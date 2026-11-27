"""Утасны дугаар эсвэл email руу илгээсэн нэг удаагийн кодоор нэвтрэх (эсвэл бүртгүүлэх)."""

from dataclasses import replace
from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import FORBIDDEN_TYPE, ProblemError
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.models import User
from angel.repositories.accounts.users import RefreshTokenRepository, UserRepository
from angel.services.accounts.auth import AuthService, IssuedSession, password_removed_notice
from angel.services.accounts.otp import (
    OtpService,
    invalid_code,
    is_phone,
    normalize_destination,
)

log = get_logger(__name__)

# Утасны шинэ бүртгэлд хуудас асуух хүртэл нэр байхгүй.
NEW_CUSTOMER_NAME = "New customer"


class OtpLoginService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        otp: OtpService,
        auth: AuthService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._otp = otp
        self._auth = auth
        self._users = UserRepository(session)

    async def request_code(self, raw_destination: str) -> None:
        """Хаяг зөв бол account байгаа эсэхээс үл хамааран үргэлж амжилттай: нэвтрэх, бүртгүүлэх
        хоёр нэг алхам тул нуух зүйл байхгүй. Ажилтны хаяг руу код илгээхгүй (тэд зөвхөн нууц
        үгээр нэвтэрнэ), гэхдээ хариу нь ижил харагдана."""
        destination = normalize_destination(raw_destination, self._settings.default_phone_region)
        async with self._session.begin():
            user = await self._find(destination)
            staff = user is not None and user.is_staff
        await self._otp.issue("login", destination, deliver=not staff)

    async def _find(self, destination: str) -> User | None:
        if is_phone(destination):
            return await self._users.get_by_phone(destination)
        return await self._users.get_by_email(destination)

    async def sign_in(
        self, raw_destination: str, code: str, guest_cart_token: str | None
    ) -> IssuedSession:
        destination = normalize_destination(raw_destination, self._settings.default_phone_region)
        await self._otp.verify("login", destination, code)
        # Код ашиглагдлаа. Хоёр дахь хүсэлт зэрэг ижил account үүсгэвэл нэгнийх нь insert амжилтгүй
        # болно: тэр нь account-ыг дахин хайна.
        for attempt in (1, 2):
            try:
                return await self._sign_in_verified(destination, guest_cart_token)
            except IntegrityError:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def _sign_in_verified(
        self, destination: str, guest_cart_token: str | None
    ) -> IssuedSession:
        now = datetime.now(UTC)
        phone = is_phone(destination)
        created = False
        async with self._session.begin():
            user = await self._find(destination)
            if user is not None and user.is_staff:
                # Код зөв байсан ч (жишээ нь тогтмол dev код) ажилтныг кодоор нэвтрүүлэхгүй, нууц
                # үгийг нь ч хөндөхгүй. Хариу нь буруу код оруулсантай адил.
                log.warning("otp_login_refused_for_staff", user_id=user.id)
                raise invalid_code()
            if user is None:
                user = await self._users.create(
                    email=None if phone else destination,
                    phone=destination if phone else None,
                    password_hash=None,
                    full_name=NEW_CUSTOMER_NAME,
                    email_verified_at=None if phone else now,
                    phone_verified_at=now if phone else None,
                )
                created = True
            elif not user.is_active:
                raise ProblemError(
                    HTTPStatus.FORBIDDEN,
                    "Энэ бүртгэлийг түр хаасан байна",
                    "Алдаа гэж үзвэл бидэнтэй холбогдоно уу.",
                    type_=FORBIDDEN_TYPE,
                )
            else:
                await self._stamp_verified(user, phone=phone, now=now)
            issued = await self._auth.start_session(
                user, guest_cart_token, method="otp", first_sign_in=created
            )
            if created and not phone:
                self._auth.queue_notice(
                    Email(
                        to=destination,
                        subject="Angel-д тавтай морилно уу",
                        body="Таны бүртгэл бэлэн боллоо.",
                    )
                )
        return replace(issued, is_new_user=created)

    async def _stamp_verified(self, user: User, *, phone: bool, now: datetime) -> None:
        if phone:
            user.phone_verified_at = user.phone_verified_at or now
        else:
            if user.email_verified_at is None:
                # Энэ хаягийг эзэмшдэгээ хэн ч батлаагүй байсан тул нууц үгээр түрүүлж бүртгүүлсэн
                # нь эзэн биш байж болно. Харин код одоо жинхэнэ эзэн энд байгааг батална. Тиймээс
                # нууц үгийг устгаж, хуучин session-уудыг дуусгана (Google-ээр нэвтрэхтэй ижил
                # дүрэм).
                if user.password_hash is not None:
                    log.info("otp_password_removed", user_id=user.id)
                    user.password_hash = None
                    await RefreshTokenRepository(self._session).revoke_all_for_user(user.id, now)
                    if user.email:
                        self._auth.queue_notice(password_removed_notice(user.email))
                user.email_verified_at = now
        self._session.add(user)
