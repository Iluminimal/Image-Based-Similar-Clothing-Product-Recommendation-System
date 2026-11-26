from datetime import datetime

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from angel.models import RefreshToken
from angel.models.security import LOGIN, SecurityEvent


class SecurityEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        user_id: int,
        type_: str,
        *,
        method: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Мөрийг session-д нэмнэ; дуудсан transaction-тайгаа хамт commit хийгдэнэ."""
        self._session.add(
            SecurityEvent(user_id=user_id, type=type_, method=method, ip=ip, user_agent=user_agent)
        )

    async def recent(self, user_id: int, limit: int) -> list[SecurityEvent]:
        rows = await self._session.execute(
            select(SecurityEvent)
            .where(SecurityEvent.user_id == user_id)
            .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def knows_device(self, user_id: int, user_agent: str | None) -> bool:
        """Энэ бүртгэлд ийм user agent-тэй нэвтрэлт урьд нь амжилттай болсон уу: хадгалсан
        refresh token, эсвэл `login` үйл явдал. Token эрт цэвэрлэгддэг тул үйл явдал нь
        төхөөрөмжийг илүү удаан санана. Амжилтгүй оролдлого тооцогдохгүй."""
        if not user_agent:
            return False
        result = await self._session.execute(
            select(
                or_(
                    exists().where(
                        RefreshToken.user_id == user_id, RefreshToken.user_agent == user_agent
                    ),
                    exists().where(
                        SecurityEvent.user_id == user_id,
                        SecurityEvent.type == LOGIN,
                        SecurityEvent.user_agent == user_agent,
                    ),
                )
            )
        )
        return bool(result.scalar_one())

    async def purge_created_before(self, before: datetime, limit: int) -> int:
        batch = select(SecurityEvent.id).where(SecurityEvent.created_at < before).limit(limit)
        result = await self._session.execute(
            delete(SecurityEvent).where(SecurityEvent.id.in_(batch))
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def delete_for_user(self, user_id: int) -> None:
        await self._session.execute(delete(SecurityEvent).where(SecurityEvent.user_id == user_id))
