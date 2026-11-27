from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from angel.models import OtpChallenge


class OtpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        purpose: str,
        destination: str,
        user_id: int | None,
        code_hash: str,
        expires_at: datetime,
    ) -> OtpChallenge:
        challenge = OtpChallenge(
            purpose=purpose,
            destination=destination,
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        self._session.add(challenge)
        await self._session.flush()
        return challenge

    async def latest(self, purpose: str, destination: str) -> OtpChallenge | None:
        """Хамгийн сүүлийн challenge (ашигласан эсэхээс үл хамаарна). Дахин илгээхээс өмнө хүлээх
        хугацааг тооцоход хэрэглэнэ."""
        result = await self._session.execute(
            select(OtpChallenge)
            .where(OtpChallenge.purpose == purpose, OtpChallenge.destination == destination)
            .order_by(OtpChallenge.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_open_for_update(self, purpose: str, destination: str) -> OtpChallenge | None:
        """Хамгийн сүүлийн, ашиглагдаагүй challenge-ийг түгжинэ: зэрэг ирсэн хоёр таамаглалыг нэг
        нэгээр нь тооцно."""
        result = await self._session.execute(
            select(OtpChallenge)
            .where(
                OtpChallenge.purpose == purpose,
                OtpChallenge.destination == destination,
                OtpChallenge.consumed_at.is_(None),
            )
            .order_by(OtpChallenge.id.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_since(self, destination: str, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(OtpChallenge)
            .where(OtpChallenge.destination == destination, OtpChallenge.created_at >= since)
        )
        return int(result.scalar_one())

    async def consume_open(self, purpose: str, destination: str, now: datetime) -> None:
        """Шинэ код хуучныг орлоно: зөвхөн хамгийн сүүлийнх нь хүчинтэй."""
        await self._session.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.purpose == purpose,
                OtpChallenge.destination == destination,
                OtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

    async def purge_created_before(self, before: datetime, limit: int) -> int:
        batch = select(OtpChallenge.id).where(OtpChallenge.created_at < before).limit(limit)
        result = await self._session.execute(delete(OtpChallenge).where(OtpChallenge.id.in_(batch)))
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def delete_for_account(self, user_id: int, destinations: list[str]) -> None:
        """Account устгахад хэрэглэнэ: нэвтрэх, нууц үг сэргээх код account-ын id-гүй, зөвхөн
        хаягтай хадгалагддаг."""
        await self._session.execute(
            delete(OtpChallenge).where(
                or_(OtpChallenge.user_id == user_id, OtpChallenge.destination.in_(destinations))
            )
        )
