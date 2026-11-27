"""Мэдэгдлийн имэйлийн outbox.

`queue_email` имэйлийг дуудсан кодын transaction дотор бичнэ. `OutboxDispatcher` дэвсгэрт илгээж,
амжилтгүй болвол хуваарийн дагуу дахин оролдоно. Имэйл "дор хаяж нэг удаа" очно: SMTP сервер хүлээж
авсны дараа процесс унавал нэг имэйл хоёр удаа очиж болно (алдагдсанаас дээр).

Нэг удаагийн код эндээс явахгүй (`OtpService` шууд илгээнэ). Хэрэглэгч хүлээж байдаг тул алдааг тэр
даруй мэдэх ёстой, бас кодыг database-д ил хадгалахгүй."""

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from angel.core.logging import get_logger
from angel.core.mail import Email, MailDeliveryError, Mailer
from angel.repositories.system.outbox import OutboxRepository

log = get_logger(__name__)

# Амжилтгүй оролдлого бүрийн дараах хүлээлт: нийт 8 оролдлого, ~35 цаг.
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
    timedelta(hours=24),
)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
# Нэг имэйл илгээх дээд хугацаа. SMTP-ийн timeout холболт, хариу бүрд тусдаа тооцогддог тул удаан
# серверт нэг имэйл хэдэн минут үргэлжилж болно.
SEND_DEADLINE = timedelta(seconds=30)
# Эзэмших хугацаа (lease) багцын бүх имэйл дээд хугацаагаа ашиглахаас урт байх ёстой. Эс бөгөөс өөр
# worker илгээгдээгүй имэйлийг дахин авч, хоёр удаа илгээнэ.
LEASE = timedelta(minutes=5)
BATCH = 8


def queue_email(session: AsyncSession, email: Email) -> None:
    """Дуудагчийн transaction дотор дуудна: өөрчлөлт commit хийгдвэл имэйл илгээгдэнэ."""
    OutboxRepository(session).add(to_address=email.to, subject=email.subject, body=email.body)


class OutboxDispatcher:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailer: Mailer) -> None:
        self._sessions = sessions
        self._mailer = mailer

    async def run_once(self) -> int:
        """Цаг нь болсон бүх имэйлийг оролдоно. Хэдийг илгээснийг буцаана."""
        sent = 0
        while True:
            async with self._sessions() as session, session.begin():
                claimed = [
                    (row.id, row.attempts, Email(row.to_address, row.subject, row.body or ""))
                    for row in await OutboxRepository(session).claim_due(BATCH, lease=LEASE)
                ]
            for email_id, attempts, email in claimed:
                sent += await self._deliver(email_id, attempts, email)
            if len(claimed) < BATCH:
                return sent

    async def _deliver(self, email_id: int, attempts: int, email: Email) -> bool:
        """SMTP дуудлагын үед transaction нээлттэй байхгүй."""
        try:
            async with asyncio.timeout(SEND_DEADLINE.total_seconds()):
                await self._mailer.send(email)
        except Exception as exc:  # нэг имэйлийн ямар ч алдаа бусдыг нь зогсоохгүй
            error = str(exc) if isinstance(exc, MailDeliveryError) else type(exc).__name__
            retry_in = RETRY_DELAYS[attempts - 1] if attempts < MAX_ATTEMPTS else None
            async with self._sessions() as session, session.begin():
                await OutboxRepository(session).mark_attempt_failed(
                    email_id, error[:100], retry_in=retry_in
                )
            if retry_in is None:
                log.error("email_gave_up", outbox_id=email_id, attempts=attempts, error=error)
            else:
                log.warning(
                    "email_will_retry",
                    outbox_id=email_id,
                    attempts=attempts,
                    retry_in_seconds=int(retry_in.total_seconds()),
                    error=error,
                )
            return False
        async with self._sessions() as session, session.begin():
            await OutboxRepository(session).mark_sent(email_id)
        return True

    async def run_forever(self, poll_seconds: float) -> None:
        while True:
            # Эхлээд хүлээнэ: апп асах үеийн ачаалалтай давхцуулахгүй.
            await asyncio.sleep(poll_seconds)
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("outbox_failed")
