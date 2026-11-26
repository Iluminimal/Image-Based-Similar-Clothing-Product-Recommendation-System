"""Ажилтны хоёр шатлалт нэвтрэлтийг (TOTP) тохируулах. Унтраах, дахин тохируулах нь зөвхөн сервер
дээрх command-оор (`reset-2fa`): хулгайлагдсан session 2FA-г өөрөө авч хаяж чадахгүй."""

import asyncio
import time
from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    FORBIDDEN_TYPE,
    INVALID_CREDENTIALS_TYPE,
    TOTP_ALREADY_ENABLED_TYPE,
    TOTP_INVALID_TYPE,
    TOTP_UNAVAILABLE_TYPE,
    UNAUTHENTICATED_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.core.secret_box import seal, unseal
from angel.core.security import hash_token, verify_password
from angel.core.totp import (
    hash_recovery_code,
    matching_step,
    new_recovery_codes,
    new_secret,
    otpauth_uri,
    qr_data_uri,
)
from angel.models import User
from angel.models import security as events
from angel.repositories.accounts.users import RefreshTokenRepository, UserRepository
from angel.schemas.accounts.two_factor import RecoveryCodes, TwoFactorSetup, TwoFactorStatus
from angel.services.accounts.auth import AuthService

log = get_logger(__name__)


class TwoFactorService:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def status(self, user_id: int) -> TwoFactorStatus:
        async with self._session.begin():
            user = await self._staff(user_id)
        return TwoFactorStatus(
            enabled=user.totp_enabled_at is not None,
            required=self._settings.staff_2fa_required,
            recovery_codes_left=len(user.totp_recovery_hashes or []),
        )

    async def setup(self, user_id: int, password: str) -> TwoFactorSetup:
        """Шинэ secret үүсгэнэ. Апп-аас гарсан эхний кодоор баталтал (`enable`) идэвхжихгүй."""
        key = self._key()
        async with self._session.begin():
            user = await self._staff(user_id)
        self._require_not_enabled(user)
        rate = await self._auth.check_failure_limit(user.identifier)
        if user.password_hash is None or not await asyncio.to_thread(
            verify_password, password, user.password_hash
        ):
            await self._auth.record_failure(user.identifier, rate)
            raise ProblemError(
                HTTPStatus.FORBIDDEN,
                "Нууц үг буруу",
                "Таны оруулсан нууц үг буруу байна.",
                type_=INVALID_CREDENTIALS_TYPE,
            )
        secret = new_secret()
        async with self._session.begin():
            user = await self._staff(user_id)
            self._require_not_enabled(user)
            user.totp_secret = seal(key, secret)
            self._session.add(user)
        uri = otpauth_uri(secret, user.identifier)
        return TwoFactorSetup(secret=secret, otpauth_uri=uri, qr_image=qr_data_uri(uri))

    async def enable(self, user_id: int, code: str, refresh_token: str | None) -> RecoveryCodes:
        """Эхний кодоор идэвхжүүлж, нөөц кодыг НЭГ УДАА буцаана. Бусад бүх нэвтрэлт дуусна: тэдгээр
        нь зөвхөн нууц үгээр үүссэн."""
        key = self._key()
        codes = new_recovery_codes()
        async with self._session.begin():
            user = await self._staff(user_id, for_update=True)
            self._require_not_enabled(user)
            secret = unseal(key, user.totp_secret) if user.totp_secret else None
            step = matching_step(secret, code, time.time()) if secret else None
            if step is None:
                raise ProblemError(
                    HTTPStatus.BAD_REQUEST,
                    "Код буруу байна",
                    "Баталгаажуулагч апп дээрх одоогийн кодыг оруулна уу.",
                    type_=TOTP_INVALID_TYPE,
                )
            user.totp_enabled_at = datetime.now(UTC)
            user.totp_last_step = step
            user.totp_recovery_hashes = [hash_recovery_code(item) for item in codes]
            self._session.add(user)
            row = (
                await self._tokens.get_by_hash(hash_token(refresh_token)) if refresh_token else None
            )
            if row is not None and row.user_id == user.id:
                await self._tokens.revoke_others(user.id, row.family_id, datetime.now(UTC))
            else:
                await self._tokens.revoke_all_for_user(user.id, datetime.now(UTC))
            self._auth.record_event(user.id, events.TWO_FACTOR_ON)
            if user.email:
                self._auth.queue_notice(
                    Email(
                        to=user.email,
                        subject="Хоёр шатлалт нэвтрэлт идэвхжлээ",
                        body="Таны бүртгэлд хоёр шатлалт нэвтрэлт идэвхжлээ. Хэрэв та өөрөө "
                        "хийгээгүй бол админд яаралтай мэдэгдэнэ үү.",
                    )
                )
        log.info("two_factor_enabled", user_id=user_id)
        return RecoveryCodes(codes=codes)

    # --- туслах функцууд ---

    def _key(self) -> str:
        """Шифрлэх түлхүүр нь тохируулсан `JWT_SECRET`. Хоосон бол (зөвхөн dev) сервер асах бүрт
        санамсаргүй түлхүүр үүсдэг тул хадгалсан secret дараа нь тайлагдахгүй: асаахаас
        татгалзана."""
        if not self._settings.jwt_secret:
            raise ProblemError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Хоёр шатлалт нэвтрэлт тохируулагдаагүй",
                "Серверийн JWT_SECRET тохируулаад дахин асаана уу.",
                type_=TOTP_UNAVAILABLE_TYPE,
            )
        return self._settings.jwt_secret

    async def _staff(self, user_id: int, *, for_update: bool = False) -> User:
        user = await (
            self._users.get_for_update(user_id) if for_update else self._users.get(user_id)
        )
        if user is None or not user.is_active:
            raise ProblemError(
                HTTPStatus.UNAUTHORIZED,
                "Нэвтрээгүй байна",
                "Дахин нэвтэрнэ үү.",
                type_=UNAUTHENTICATED_TYPE,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_staff:
            raise ProblemError(
                HTTPStatus.FORBIDDEN,
                "Зөвхөн ажилтан",
                "Хоёр шатлалт нэвтрэлт ажилтны бүртгэлд зориулагдсан.",
                type_=FORBIDDEN_TYPE,
            )
        return user

    @staticmethod
    def _require_not_enabled(user: User) -> None:
        if user.totp_enabled_at is not None:
            raise ProblemError(
                HTTPStatus.CONFLICT,
                "Хоёр шатлалт нэвтрэлт идэвхтэй байна",
                "Дахин тохируулах бол сервер хариуцсан хүнд хандана уу.",
                type_=TOTP_ALREADY_ENABLED_TYPE,
            )
