import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.security import hash_password
from angel.models import User
from angel.models.user import ROLE_ADMIN, STAFF_ROLES
from angel.repositories.accounts.users import RefreshTokenRepository, UserRepository


async def provision_staff(
    session: AsyncSession,
    *,
    email: str,
    password: str | None,
    full_name: str,
    role: str = ROLE_ADMIN,
) -> tuple[User, bool]:
    """Ажилтан (админ эсвэл агуулахын ажилтан) үүсгэнэ, эсвэл энэ email-тэй бүртгэл аль хэдийн
    байвал түүнийг `role`-д оноож дэвшүүлнэ.

    Хэрэглэгч болон шинээр үүссэн эсэхийг буцаана. Одоо байгаа бүртгэл нууц үг өгөөгүй бол
    хуучнаа хадгална. Бүртгүүлэх замаар ажилтан хэзээ ч үүсэхгүй: энэ бол цорын ганц зам."""
    if role not in STAFF_ROLES:
        raise ValueError(f"{role!r} is not a staff role")
    email = email.strip().lower()
    password_hash = await asyncio.to_thread(hash_password, password) if password else None
    async with session.begin():
        repository = UserRepository(session)
        user = await repository.get_by_email(email)
        if user is None:
            if password_hash is None:
                raise ValueError(f"no account for {email}: a password is needed to create one")
            # Command ажиллуулсан оператор хаягийг баталж байна.
            user = await repository.create(
                email=email,
                password_hash=password_hash,
                full_name=full_name,
                role=role,
                email_verified_at=datetime.now(UTC),
            )
            return user, True
        if password_hash is None and user.password_hash is None:
            # Ажилтан кодоор ч, Google-ээр ч нэвтэрдэггүй: нууц үггүй бол хаанаас ч орохгүй.
            raise ValueError(f"{email} has no password: run without --keep-password to set one")
        if user.role != role or password_hash is not None:
            # Өмнөх нэвтрэлтүүд (кодоор, Google-ээр үүссэн эсвэл өөр хүнийх) шинэ эрхийг өвлөхгүй.
            await RefreshTokenRepository(session).revoke_all_for_user(user.id, datetime.now(UTC))
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        user.role = role
        user.is_active = True
        if password_hash is not None:
            user.password_hash = password_hash
        return user, False


async def set_role(session: AsyncSession, *, email: str, role: str) -> User | None:
    async with session.begin():
        user = await UserRepository(session).get_by_email(email.strip().lower())
        if user is not None:
            user.role = role
        return user


async def reset_two_factor(session: AsyncSession, *, email: str) -> User | None:
    """Утсаа алдсан ажилтны 2FA-г арилгаж, бүх нэвтрэлтийг дуусгана. Дараагийн нэвтрэлтийн дараа
    дахин тохируулна."""
    async with session.begin():
        user = await UserRepository(session).get_by_email(email.strip().lower())
        if user is not None:
            user.totp_secret = None
            user.totp_enabled_at = None
            user.totp_last_step = None
            user.totp_recovery_hashes = None
            await RefreshTokenRepository(session).revoke_all_for_user(user.id, datetime.now(UTC))
        return user
