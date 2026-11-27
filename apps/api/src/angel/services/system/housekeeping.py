"""Хугацаа нь өнгөрсөн өгөгдлийг цаг тутам цэвэрлэнэ. Энгийн DELETE-үүд тул хэд хэдэн API process
зэрэг ажиллуулахад аюулгүй; том хүснэгтийг удаан түгжихгүйн тулд багцаар устгана.

Хугацаанууд нь дэлгүүрийн бодлого (`*_RETENTION_*` тохиргоо). Захиалга, ажилтны үйлдлийн журнал
эндээс устдаггүй. Орхигдсон зочны сагсыг `OrderExpirer` устгадаг."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from angel.core.config import Settings
from angel.core.logging import get_logger
from angel.repositories.accounts.otp import OtpRepository
from angel.repositories.accounts.security_events import SecurityEventRepository
from angel.repositories.accounts.users import RefreshTokenRepository
from angel.repositories.system.outbox import OutboxRepository

log = get_logger(__name__)

BATCH = 1000
# Асснаас хойш эхний цэвэрлэгээ хүртэл хүлээх хугацаа: dev-д сервер байнга дахин асдаг ч цэвэрлэгээ
# нэг удаа ч гэсэн ажиллана.
FIRST_RUN_SECONDS = 60


class Housekeeper:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._settings = settings

    async def run_once(self) -> dict[str, int]:
        """Төрөл бүрээс хэдийг устгасныг буцаана."""
        now = datetime.now(UTC)
        settings = self._settings
        otp_before = now - timedelta(hours=settings.otp_retention_hours)
        tokens_before = now - timedelta(days=settings.refresh_token_retention_days)
        events_before = now - timedelta(days=settings.security_event_retention_days)
        sent_before = now - timedelta(days=settings.email_sent_retention_days)
        failed_before = now - timedelta(days=settings.email_failed_retention_days)
        removed = {
            "one_time_codes": await self._in_batches(
                lambda s: OtpRepository(s).purge_created_before(otp_before, BATCH)
            ),
            "refresh_tokens": await self._in_batches(
                lambda s: RefreshTokenRepository(s).purge_expired_before(tokens_before, now, BATCH)
            ),
            "security_events": await self._in_batches(
                lambda s: SecurityEventRepository(s).purge_created_before(events_before, BATCH)
            ),
            "sent_emails": await self._in_batches(
                lambda s: OutboxRepository(s).purge("sent", sent_before, BATCH)
            ),
            "failed_emails": await self._in_batches(
                lambda s: OutboxRepository(s).purge("failed", failed_before, BATCH)
            ),
        }
        if any(removed.values()):
            log.info("housekeeping", **removed)
        return removed

    async def _in_batches(self, purge: Callable[[AsyncSession], Awaitable[int]]) -> int:
        total = 0
        while True:
            async with self._sessions() as session, session.begin():
                removed = await purge(session)
            total += removed
            if removed < BATCH:
                return total

    async def run_forever(self) -> None:
        wait = min(FIRST_RUN_SECONDS, self._settings.housekeeping_interval_seconds)
        while True:
            await asyncio.sleep(wait)
            wait = self._settings.housekeeping_interval_seconds
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("housekeeping_failed")
