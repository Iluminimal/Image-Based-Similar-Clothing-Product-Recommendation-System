import uuid
from datetime import datetime

from sqlalchemy import and_, delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from angel.models import Address, OAuthIdentity, RefreshToken, User
from angel.models.user import ROLE_CUSTOMER


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_for_update(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id, with_for_update=True, populate_existing=True)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self._session.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def providers(self, user_id: int) -> list[str]:
        result = await self._session.execute(
            select(OAuthIdentity.provider)
            .where(OAuthIdentity.user_id == user_id)
            .order_by(OAuthIdentity.provider)
        )
        return list(result.scalars())

    async def get_by_identity(self, provider: str, subject: str) -> User | None:
        result = await self._session.execute(
            select(User)
            .join(OAuthIdentity, OAuthIdentity.user_id == User.id)
            .where(OAuthIdentity.provider == provider, OAuthIdentity.subject == subject)
        )
        return result.scalar_one_or_none()

    async def add_identity(
        self, *, user_id: int, provider: str, subject: str, email: str
    ) -> OAuthIdentity:
        identity = OAuthIdentity(user_id=user_id, provider=provider, subject=subject, email=email)
        self._session.add(identity)
        await self._session.flush()
        return identity

    async def create(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
        password_hash: str | None,
        full_name: str,
        role: str = ROLE_CUSTOMER,
        email_verified_at: datetime | None = None,
        phone_verified_at: datetime | None = None,
    ) -> User:
        user = User(
            email=email,
            phone=phone,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            email_verified_at=email_verified_at,
            phone_verified_at=phone_verified_at,
        )
        self._session.add(user)
        await self._session.flush()
        return user


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: int,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> RefreshToken:
        """`last_used_at` нь `created_at`-тай адил database-ийн цаг: хоёр цаг зөрөхгүй."""
        token = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
            last_used_at=func.now(),
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def lock_login(self, token_hash: str) -> RefreshToken | None:
        """Token-ийг олж, түүний нэвтрэлтийг transaction дуустал түгжээд мөрийг дахин уншина.
        Нэг нэвтрэлтийн refresh, гаралт нэг нэгээрээ явна."""
        found = await self.get_by_hash(token_hash)
        if found is None:
            return None
        await self._lock_family(found.family_id)
        result = await self._session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _lock_family(self, family_id: uuid.UUID) -> None:
        # Мөрийн түгжээ хангалтгүй: нэг нэвтрэлтийн хоёр token бие биенийхээ мөрийг шинэчлэх гэж
        # deadlock болно, мөн дөнгөж нэмж буй мөр нь гаралтын UPDATE-д харагдахгүй.
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(str(family_id), 0)))
        )

    async def rotated_after(self, token: RefreshToken, used_at: datetime) -> bool:
        """`token`-ийг сольсноос хойш энэ нэвтрэлт цааш явсан уу."""
        result = await self._session.execute(
            select(RefreshToken.id)
            .where(
                RefreshToken.family_id == token.family_id,
                RefreshToken.id != token.id,
                RefreshToken.used_at > used_at,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def retire_siblings(self, token: RefreshToken, at: datetime) -> None:
        """Нэвтрэлтийн бусад ашиглагдаагүй token-ийг ашигласанд тооцно."""
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token.family_id,
                RefreshToken.id != token.id,
                RefreshToken.used_at.is_(None),
                RefreshToken.revoked_at.is_(None),
            )
            .values(used_at=at)
        )

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def active_sessions(
        self, user_id: int, now: datetime
    ) -> list[tuple[RefreshToken, datetime]]:
        """Нээлттэй нэвтрэлт бүрт нэг мөр: хамгийн сүүлийн token болон нэвтрэлт эхэлсэн цаг."""
        began = (
            select(RefreshToken.family_id, func.min(RefreshToken.created_at).label("began"))
            .where(RefreshToken.user_id == user_id)
            .group_by(RefreshToken.family_id)
            .subquery()
        )
        result = await self._session.execute(
            select(RefreshToken, began.c.began)
            .join(began, began.c.family_id == RefreshToken.family_id)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.used_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.id.desc())
        )
        # Богино хугацаанд нэг нэвтрэлт хоёр ашиглагдаагүй token-той байж болно: нэг мөр л харуулна.
        newest: dict[uuid.UUID, tuple[RefreshToken, datetime]] = {}
        for token, started in result.all():
            newest.setdefault(token.family_id, (token, started))
        return list(newest.values())

    async def revoke_family_of_user(
        self, user_id: int, family_id: uuid.UUID, now: datetime
    ) -> bool:
        """Нэг нэвтрэлтийг дуусгана (зөвхөн өөрийнх бол). False: нээлттэй нэвтрэлт олдсонгүй."""
        await self._lock_family(family_id)
        result = await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def revoke_others(self, user_id: int, keep: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id != keep,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> None:
        """Хэрэглэгчийн бүх нэвтрэлтийг дуусгана: нууц үг солигдоход хэрэглэнэ."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def purge_expired_before(self, before: datetime, now: datetime, limit: int) -> int:
        """`before`-оос өмнө дууссан token-уудын нэг багц. Амьд нэвтрэлтийн эхний мөр үлдэнэ:
        "хэзээнээс нэвтэрсэн" гэдэг үүнээс гардаг. Дууссан token дахин ирэхэд ямар ч байсан
        татгалздаг тул хулгайг илрүүлэх чадвар буурахгүй."""
        first, live = aliased(RefreshToken), aliased(RefreshToken)
        begins_a_live_login = and_(
            ~exists().where(first.family_id == RefreshToken.family_id, first.id < RefreshToken.id),
            exists().where(
                live.family_id == RefreshToken.family_id,
                live.used_at.is_(None),
                live.revoked_at.is_(None),
                live.expires_at > now,
            ),
        )
        batch = (
            select(RefreshToken.id)
            .where(RefreshToken.expires_at < before, ~begins_a_live_login)
            .limit(limit)
        )
        result = await self._session.execute(delete(RefreshToken).where(RefreshToken.id.in_(batch)))
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def delete_all_for_user(self, user_id: int) -> None:
        await self._session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )


class AddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[Address]:
        result = await self._session.execute(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.id)
        )
        return list(result.scalars())

    async def get(self, user_id: int, address_id: int) -> Address | None:
        """Эзэмшигчээр хязгаарлана: өөр хүний id нь байхгүй id-аас ялгагдахгүй."""
        result = await self._session.execute(
            select(Address)
            .where(Address.id == address_id, Address.user_id == user_id)
            # Checkout нэг session-д хоёр удаа уншдаг: хоёр дахь нь хуучин утга байж болохгүй.
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def count(self, user_id: int) -> int:
        return len(await self.list_for_user(user_id))

    async def clear_default(self, user_id: int) -> None:
        await self._session.execute(
            update(Address)
            .where(Address.user_id == user_id, Address.is_default.is_(True))
            .values(is_default=False)
        )
        await self._session.flush()

    async def add(self, address: Address) -> Address:
        self._session.add(address)
        await self._session.flush()
        return address

    async def delete(self, address: Address) -> None:
        await self._session.delete(address)
        await self._session.flush()
