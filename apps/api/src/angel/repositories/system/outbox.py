"""`email_outbox`-ийн уншилт, бичилт."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from angel.models import OutboxEmail


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, *, to_address: str, subject: str, body: str) -> None:
        """Дуудагчийн transaction-ийн хэсэг."""
        self._session.add(OutboxEmail(to_address=to_address, subject=subject, body=body))

    async def claim_due(self, limit: int, *, lease: timedelta) -> list[OutboxEmail]:
        """Илгээх цаг нь болсон мөрүүдийг `lease` хугацаанд эзэмшинэ. Өөр worker-ийн түгжсэнийг
        алгасдаг тул хоёр процесс нэг имэйлийг зэрэг авахгүй; эзэмшсэн worker унавал хугацаа
        дуусмагц дахин авагдана. Дуудагч тэр даруй commit хийнэ."""
        rows = await self._session.execute(
            select(OutboxEmail)
            .where(OutboxEmail.status == "pending", OutboxEmail.next_attempt_at <= func.now())
            .order_by(OutboxEmail.next_attempt_at, OutboxEmail.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claimed = list(rows.scalars())
        if claimed:
            await self._session.execute(
                update(OutboxEmail)
                .where(OutboxEmail.id.in_([row.id for row in claimed]))
                .values(attempts=OutboxEmail.attempts + 1, next_attempt_at=func.now() + lease)
            )
            for row in claimed:
                await self._session.refresh(row)
        return claimed

    async def mark_sent(self, email_id: int) -> None:
        await self._session.execute(
            update(OutboxEmail)
            .where(OutboxEmail.id == email_id)
            .values(status="sent", sent_at=func.now(), body=None, last_error=None)
        )

    async def mark_attempt_failed(
        self, email_id: int, error: str, *, retry_in: timedelta | None
    ) -> None:
        """`retry_in` None бол оролдлого дууссан: `failed`."""
        values: dict[str, object] = {"last_error": error}
        if retry_in is None:
            values["status"] = "failed"
        else:
            values["next_attempt_at"] = func.now() + retry_in
        await self._session.execute(
            update(OutboxEmail)
            .where(OutboxEmail.id == email_id, OutboxEmail.status == "pending")
            .values(**values)
        )

    # --- оператор ---

    async def counts(self) -> dict[str, int]:
        rows = await self._session.execute(
            select(OutboxEmail.status, func.count()).group_by(OutboxEmail.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def failed(self, limit: int) -> list[OutboxEmail]:
        rows = await self._session.execute(
            select(OutboxEmail)
            .where(OutboxEmail.status == "failed")
            .order_by(OutboxEmail.id.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def requeue_failed(self) -> int:
        result = await self._session.execute(
            update(OutboxEmail)
            .where(OutboxEmail.status == "failed")
            .values(status="pending", attempts=0, next_attempt_at=func.now())
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    # --- цэвэрлэгээ ---

    async def purge(self, status: str, before: datetime, limit: int) -> int:
        """`before`-оос хойш өөрчлөгдөөгүй `sent` эсвэл `failed` мөрүүдийн нэг багцыг устгана."""
        batch = (
            select(OutboxEmail.id)
            .where(OutboxEmail.status == status, OutboxEmail.updated_at < before)
            .limit(limit)
        )
        result = await self._session.execute(delete(OutboxEmail).where(OutboxEmail.id.in_(batch)))
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def forget_finished(self, addresses: Sequence[str]) -> None:
        """Бүртгэл устгахад: илгээгдсэн, унасан мөрүүд хаягийг хадгалах шалтгаангүй. Хүлээж буй нь
        (жишээ нь төлбөр буцаасан мэдэгдэл) очсоны дараа цэвэрлэгээгээр устна."""
        await self._session.execute(
            delete(OutboxEmail).where(
                OutboxEmail.to_address.in_(addresses), OutboxEmail.status != "pending"
            )
        )
