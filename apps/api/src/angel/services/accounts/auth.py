"""Имэйл, нууц үгээр бүртгүүлэх ба нэвтрэх, refresh token сэлгэх, гарах.

Бусад нэвтрэх зам (нэг удаагийн код, Google, нууц үг сэргээх) ч session-оо эндээс үүсгэдэг тул
session-ий дүрэм нэг газар байна.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    EMAIL_TAKEN_TYPE,
    INVALID_CREDENTIALS_TYPE,
    TOTP_INVALID_TYPE,
    TOTP_REQUIRED_TYPE,
    UNAUTHENTICATED_TYPE,
    WEAK_PASSWORD_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.core.passwords import WeakReason, weakness
from angel.core.rate_limit import RATE_LIMITED_TYPE, Rate, RateLimiter
from angel.core.security import (
    AccessToken,
    burn_password_check,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_opaque_token,
    verify_password,
)
from angel.models import User
from angel.models import security as events
from angel.repositories.accounts.security_events import SecurityEventRepository
from angel.repositories.accounts.users import RefreshTokenRepository, UserRepository
from angel.repositories.catalog.products import ProductRepository
from angel.repositories.commerce.carts import CartRepository
from angel.schemas.accounts.auth import LoginRequest, RegisterRequest, Role, UserOut
from angel.services.accounts.devices import describe_device
from angel.services.accounts.second_factor import consume_second_factor
from angel.services.commerce.cart import merge_guest_cart
from angel.services.system.outbox import queue_email

log = get_logger(__name__)

# Browser шинэ cookie авч амжаагүй байхдаа дахин хүсэлт илгээж болно: хуудас шилжсэн, сүлжээ
# тасарсан, хоёр tab зэрэг сэргээсэн гэх мэт. Энэ богино хугацаанд нэвтрэлт цаашаа үргэлжлээгүй бол
# дөнгөж сольсон token-д дахин шинэ token өгнө. Үүнээс хойш дахин ирсэн token-ыг алдагдсан гэж үзнэ.
REUSE_GRACE = timedelta(seconds=10)
# Ашиглагдалгүй орлогдсон token-ыг, түүнийг орлосон солилтоос өмнөх цагаар тэмдэглэнэ. Ингэснээр
# `rotated_after` нь жинхэнэ солигдсоныг орлогдсоноос ялгана.
_RETIRED_BEFORE = timedelta(microseconds=1)
_LOGIN_FAILURES = "login-fail"
# Өдрийн хязгаар: удаан, олон газраас таах оролдлогыг 5 минутын цонх барьж чаддаггүй.
_LOGIN_FAILURES_DAILY = "login-fail-day"


@dataclass(frozen=True)
class ClientInfo:
    """ "Миний төхөөрөмжүүд" жагсаалтад харагдах нэвтрэлтийн мэдээлэл, нэвтрэлтийг үүсгэсэн
    хүсэлтээс авсан."""

    user_agent: str | None = None
    ip: str | None = None


@dataclass(frozen=True)
class UserView:
    """Холбосон нэвтрэх provider-уудтай нь хэрэглэгч: API account-ын юуг харуулдгийг энэ
    тодорхойлно."""

    user: User
    providers: list[str]

    def out(self) -> UserOut:
        user = self.user
        return UserOut(
            id=user.id,
            email=user.email,
            phone=user.phone,
            email_verified=user.email_verified_at is not None,
            phone_verified=user.phone_verified_at is not None,
            full_name=user.full_name,
            role=cast(Role, user.role),
            avatar_url=user.avatar_url,
            has_password=user.password_hash is not None,
            providers=self.providers,
        )


@dataclass(frozen=True)
class IssuedSession:
    access: AccessToken
    refresh_token: str
    refresh_max_age: int
    user: UserView
    is_new_user: bool = False


def _invalid_credentials() -> ProblemError:
    return ProblemError(
        HTTPStatus.UNAUTHORIZED,
        "Имэйл эсвэл нууц үг буруу байна",
        type_=INVALID_CREDENTIALS_TYPE,
    )


_WEAK_DETAIL: dict[WeakReason, str] = {
    "common": "Энэ нууц үг хэт түгээмэл тул таамаглахад амархан. Өөр, урт нууц үг сонгоно уу.",
    "repeated": "Нууц үг хэт давтагдсан тэмдэгтүүдээс бүрдэж байна. Өөр нууц үг сонгоно уу.",
    "contains_identity": "Нууц үг таны имэйл эсвэл нэрийг агуулж байна. Өөр нууц үг сонгоно уу.",
}


def ensure_strong_password(
    password: str, *, email: str | None = None, full_name: str | None = None
) -> None:
    """Сул нууц үгийг 422-оор татгалзана (шалтгаан нь `reason` өргөтгөлд)."""
    reason = weakness(password, email=email, full_name=full_name)
    if reason is not None:
        raise ProblemError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Нууц үг хэт сул байна",
            _WEAK_DETAIL[reason],
            type_=WEAK_PASSWORD_TYPE,
            extensions={"reason": reason},
        )


def _unauthenticated(detail: str = "Дахин нэвтэрнэ үү.") -> ProblemError:
    return ProblemError(
        HTTPStatus.UNAUTHORIZED,
        "Нэвтрээгүй байна",
        detail,
        type_=UNAUTHENTICATED_TYPE,
        headers={"WWW-Authenticate": "Bearer"},
    )


def password_removed_notice(email: str) -> Email:
    """Баталгаажаагүй хаягтай account-ын эзэмшлийг код эсвэл Google-ээр батлахад хуучин нууц үг
    устдаг. Эзэн нь үүнийг мэдэх ёстой."""
    return Email(
        to=email,
        subject="Таны бүртгэлийн нууц үг хасагдлаа",
        body="Таны имэйл хаяг баталгаажаагүй байсан тул аюулгүй байдлын үүднээс өмнөх нууц үгийг "
        "хасаж, бусад бүх төхөөрөмжөөс гаргалаа. «Миний мэдээлэл» хуудаснаас шинэ нууц үг "
        "тохируулж болно.",
    )


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        jwt_secret: str,
        limiter: RateLimiter,
        client: ClientInfo | None = None,
    ) -> None:
        self._client = client or ClientInfo()
        self._session = session
        self._settings = settings
        self._secret = jwt_secret
        self._limiter = limiter
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._events = SecurityEventRepository(session)

    # --- аюулгүй байдлын үйл явдал, мэдэгдэл ---

    def record_event(self, user_id: int, type_: str, *, method: str | None = None) -> None:
        """Энэ хүсэлтийн төхөөрөмж, IP-тэй үйл явдлыг дуудсан кодын transaction дотор нэмнэ."""
        self._events.add(
            user_id,
            type_,
            method=method,
            ip=self._client.ip,
            user_agent=self._client.user_agent,
        )

    def queue_notice(self, email: Email) -> None:
        """Мэдэгдлийг дуудсан кодын transaction дотор outbox-д бичнэ: өөрчлөлт буцвал хэнд ч
        мэдэгдэхгүй, commit хийгдвэл мэдэгдэл алдагдахгүй."""
        queue_email(self._session, email)

    async def register(
        self, request: RegisterRequest, guest_cart_token: str | None
    ) -> IssuedSession:
        ensure_strong_password(request.password, email=request.email, full_name=request.full_name)
        # Hash тооцох нь CPU их ашигладаг (~50 ms) тул event loop дээр ажиллуулахгүй.
        password_hash = await asyncio.to_thread(hash_password, request.password)
        async with self._session.begin():
            if await self._users.get_by_email(request.email) is not None:
                raise self._email_taken()
            try:
                user = await self._users.create(
                    email=request.email, password_hash=password_hash, full_name=request.full_name
                )
            except IntegrityError:  # зэрэг явсан өөр бүртгэл түрүүлсэн
                raise self._email_taken() from None
            await self._merge_cart(user.id, guest_cart_token)
            issued = await self._issue(user, family_id=uuid.uuid4())
            self.queue_notice(
                Email(
                    to=request.email,
                    subject="Angel-д тавтай морилно уу",
                    body=f"Сайн байна уу, {user.full_name}! Таны бүртгэл бэлэн боллоо.",
                )
            )
        return issued

    async def login(self, request: LoginRequest, guest_cart_token: str | None) -> IssuedSession:
        # Нэг email-ийн амжилтгүй оролдлогыг тоолно (route дээрх client-ийн хязгаараас тусдаа).
        # Ингэснээр нэг account-ын нууц үгийг олон газраас таах халдлага удаашрана.
        failure_rate = await self.check_failure_limit(request.email)
        async with self._session.begin():
            user = await self._users.get_by_email(request.email)
        # Account байхгүй ч ямар нэг hash-ийг заавал шалгана: ингэснээр бүртгэлгүй email буруу нууц
        # үгтэй ижил хугацаа авна. Hash байхгүй account бол зөвхөн Google-ээр нэвтэрдэг account. Тэр
        # ч бусад амжилтгүй нэвтрэлттэй ижил харагдана. Тиймээс ямар email бүртгэлтэй, яаж
        # нэвтэрдгийг форм хэзээ ч илчлэхгүй.
        if user is None or not user.is_active or user.password_hash is None:
            await asyncio.to_thread(burn_password_check, request.password)
            await self._count_failure(request.email, failure_rate)
            raise _invalid_credentials()
        if not await asyncio.to_thread(verify_password, request.password, user.password_hash):
            await self._record_wrong_credentials(user, request.email, failure_rate)
            log.info("login_failed", email_hash=hash_token(request.email)[:12])
            raise _invalid_credentials()
        second_factor = user.totp_enabled_at is not None
        if second_factor and not request.totp_code:
            # Зөвхөн зөв нууц үгийн дараа асуудаг. Амжилтгүй оролдлогын тоолуурыг тэглэхгүй: бүтэн
            # нэвтэрсэн үед л тэглэнэ.
            raise ProblemError(
                HTTPStatus.UNAUTHORIZED,
                "Баталгаажуулах код оруулна уу",
                "Баталгаажуулагч апп дээрх код эсвэл нөөц кодоо оруулна уу.",
                type_=TOTP_REQUIRED_TYPE,
            )
        new_hash = (
            await asyncio.to_thread(hash_password, request.password)
            if needs_rehash(user.password_hash)
            else None
        )
        issued: IssuedSession | None = None
        async with self._session.begin():
            accepted = True
            if second_factor:
                # Мөрийг түгжинэ: нэг кодтой хоёр хүсэлт зэрэг ирсэн ч хоёулаа нэвтрэхгүй.
                locked = await self._users.get_for_update(user.id)
                assert locked is not None
                assert request.totp_code is not None
                user = locked
                accepted = consume_second_factor(user, request.totp_code, self._secret)
            if accepted:
                if new_hash is not None:
                    user.password_hash = new_hash
                self._session.add(user)
                issued = await self.start_session(user, guest_cart_token)
        if issued is None:
            await self._record_wrong_credentials(user, request.email, failure_rate)
            raise ProblemError(
                HTTPStatus.UNAUTHORIZED,
                "Баталгаажуулах код буруу байна",
                "Баталгаажуулагч апп дээрх одоогийн кодыг оруулна уу.",
                type_=TOTP_INVALID_TYPE,
            )
        await self._limiter.reset(_LOGIN_FAILURES, hash_token(request.email))
        return issued

    async def refresh(self, refresh_token: str | None) -> IssuedSession:
        if not refresh_token:
            raise _unauthenticated()
        failure: str | None = None
        issued: IssuedSession | None = None
        async with self._session.begin():
            row = await self._tokens.lock_login(hash_token(refresh_token))
            now = datetime.now(UTC)  # түгжээ авсны дараах цаг: дараалал зөв хадгалагдана
            if row is None:
                failure = "unknown"
            elif row.revoked_at is not None or row.expires_at <= now:
                failure = "revoked_or_expired"
            elif row.used_at is not None and now - row.used_at > REUSE_GRACE:
                # Аль хэдийн солигдсон token дахин ашиглагдаж байна. Хулгайлагдсан гэж үзээд тэр
                # нэвтрэлтээс үүссэн бүх session-ийг дуусгана.
                await self._tokens.revoke_family(row.family_id, now)
                log.warning("refresh_token_reuse", user_id=row.user_id)
                failure = "reuse_detected"
            elif row.used_at is not None and await self._tokens.rotated_after(row, row.used_at):
                failure = "reused"
            else:
                user = await self._users.get(row.user_id)
                if user is None or not user.is_active:
                    failure = "inactive"
                else:
                    if row.used_at is None:
                        row.used_at = now
                        await self._tokens.retire_siblings(row, now - _RETIRED_BEFORE)
                    else:
                        # `used_at`-ийг хөдөлгөхгүй: цонх сунахгүй.
                        log.info("refresh_reissued", user_id=row.user_id)
                    issued = await self._issue(user, family_id=row.family_id)
        # Алдааг блокийн дараа шиднэ: ингэснээр дээрх family-г хүчингүй болгосон өөрчлөлт commit
        # хийгдсэн байна.
        if issued is None:
            log.info("refresh_rejected", reason=failure)
            raise _unauthenticated()
        return issued

    async def logout(self, refresh_token: str | None) -> None:
        """Cookie-ийн session-ийг дуусгана. Үргэлж амжилттай: хоёр удаа гарсан ч зүгээр."""
        if not refresh_token:
            return
        async with self._session.begin():
            row = await self._tokens.lock_login(hash_token(refresh_token))
            if row is not None:
                await self._tokens.revoke_family(row.family_id, datetime.now(UTC))

    async def me(self, user_id: int) -> UserView:
        async with self._session.begin():
            user = await self._users.get(user_id)
            if user is None or not user.is_active:
                raise _unauthenticated()
            return UserView(user, await self._users.providers(user.id))

    # --- амжилтгүй оролдлогын хязгаар (нууц үг шалгадаг бүртгэлийн endpoint-уудтай хуваалцана) ---

    async def check_failure_limit(self, email: str) -> Rate:
        """Энэ email сүүлийн үед хэт олон буруу нууц үгтэй байвал 429 шиднэ."""
        rate = Rate.parse(self._settings.rate_limit_login_email)
        daily = Rate.parse(self._settings.rate_limit_login_email_daily)
        if self._settings.rate_limit_enabled:
            for name, limit in ((_LOGIN_FAILURES_DAILY, daily), (_LOGIN_FAILURES, rate)):
                decision = await self._limiter.peek(name, hash_token(email), limit)
                if decision.allowed:
                    continue
                raise ProblemError(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    "Олон удаа буруу оролдлоо",
                    f"{decision.reset_seconds} секундын дараа дахин оролдоно уу.",
                    type_=RATE_LIMITED_TYPE,
                    headers={"Retry-After": str(decision.reset_seconds)},
                )
        return rate

    async def record_failure(self, email: str, rate: Rate) -> None:
        await self._count_failure(email, rate)

    async def _record_wrong_credentials(self, user: User, email: str, rate: Rate) -> None:
        """Бодит account дээр буруу нууц үг эсвэл код орсон: тоолж, журналд бичнэ. Өдрийн хязгаарт
        яг хүрсэн бол эзэнд мэдэгдэнэ."""
        limit_reached = await self._count_failure(email, rate, user)
        async with self._session.begin():
            self.record_event(user.id, events.LOGIN_FAILED, method="password")
            if limit_reached is not None:
                self.queue_notice(limit_reached)

    async def clear_failures(self, email: str, *, include_daily: bool = False) -> None:
        """Амжилттай нэвтэрвэл богино хугацааны тоолуурыг цэвэрлэнэ. Өдрийн тоолуурыг үлдээнэ:
        халдагч нэг амжилтаар тоогоо тэглэж чадах ёсгүй. Зөвхөн нууц үг солих, сэргээх үед
        тэглэнэ."""
        await self._limiter.reset(_LOGIN_FAILURES, hash_token(email))
        if include_daily:
            await self._limiter.reset(_LOGIN_FAILURES_DAILY, hash_token(email))

    async def issue_session(self, user: User) -> IssuedSession:
        """Сагсанд хүрэхгүйгээр шинэ нэвтрэлт (шинэ refresh family) үүсгэнэ. Дуудсан кодын
        transaction дотор ажиллана."""
        return await self._issue(user, family_id=uuid.uuid4())

    async def start_session(
        self,
        user: User,
        guest_cart_token: str | None,
        *,
        method: str = "password",
        first_sign_in: bool = False,
    ) -> IssuedSession:
        """Шинэ нэвтрэлт: зочны сагс account-ынхтай нэгдэж, шинэ refresh family эхэлнэ. Нэвтрэлтийг
        аюулгүй байдлын журналд бичнэ. Энэ төхөөрөмжөөс өмнө нь нэвтэрч байгаагүй бол эзэнд
        мэдэгдэнэ. Account дөнгөж үүссэн бол (`first_sign_in`) харьцуулах өмнөх төхөөрөмж
        байхгүй. Үүнийг хадгалсан мөрүүдээс таахгүй, учир нь тэдгээр цэвэрлэгддэг.
        Дуудсан кодын transaction дотор ажиллана (нууц үг, код, Google)."""
        await self._merge_cart(user.id, guest_cart_token)
        # Шинэ token нэмэхээс өмнө: тэгэхгүй бол энэ нэвтрэлт өөрөө "танил төхөөрөмж" болно.
        known = await self._events.knows_device(user.id, self._client.user_agent)
        issued = await self._issue(user, family_id=uuid.uuid4())
        self.record_event(user.id, events.LOGIN, method=method)
        if not first_sign_in and not known:
            self.record_event(user.id, events.NEW_DEVICE, method=method)
            self._notify_new_device(user)
        return issued

    # --- туслах функцууд ---

    async def _issue(self, user: User, *, family_id: uuid.UUID) -> IssuedSession:
        refresh_token = new_opaque_token()
        max_age = int(timedelta(days=self._settings.refresh_token_ttl_days).total_seconds())
        if user.is_staff:
            # Ажилтны account илүү их эрхтэй тул идэвхгүй бол ердийн хэрэглэгчээс эрт дуусна.
            max_age = min(max_age, self._settings.staff_refresh_ttl_hours * 3600)
        now = datetime.now(UTC)
        await self._tokens.add(
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_token(refresh_token),
            expires_at=now + timedelta(seconds=max_age),
            user_agent=self._client.user_agent,
            ip=self._client.ip,
        )
        access = create_access_token(user.id, self._secret, self._settings.access_token_ttl_seconds)
        view = UserView(user, await self._users.providers(user.id))
        return IssuedSession(access, refresh_token, max_age, view)

    async def _merge_cart(self, user_id: int, guest_cart_token: str | None) -> None:
        await merge_guest_cart(
            CartRepository(self._session),
            ProductRepository(self._session),
            user_id=user_id,
            guest_token=guest_cart_token,
            max_per_line=self._settings.cart_max_quantity,
        )

    async def _count_failure(
        self, email: str, rate: Rate, user: User | None = None
    ) -> Email | None:
        """Оролдлогыг тоолно. Эзэнд илгээх мэдэгдэл байвал буцаана (дуудсан код өөрийн transaction
        дотор дараалалд оруулна)."""
        if not self._settings.rate_limit_enabled:
            return None
        await self._limiter.hit(_LOGIN_FAILURES, hash_token(email), rate)
        daily = await self._limiter.hit(
            _LOGIN_FAILURES_DAILY,
            hash_token(email),
            Rate.parse(self._settings.rate_limit_login_email_daily),
        )
        # Хязгаарт яг хүрэх үед л эзэнд мэдэгдэнэ (өдөрт нэгээс олонгүй).
        if user is not None and user.email and daily.allowed and daily.remaining == 0:
            return Email(
                to=user.email,
                subject="Таны бүртгэлд олон удаа буруу нууц үг оруулжээ",
                body="Таны бүртгэлд буруу нууц үгээр олон удаа нэвтрэхийг оролдсон тул "
                "нэвтрэхийг түр хаалаа. Хэрэв та өөрөө биш бол нууц үгээ солино уу.",
            )
        return None

    def _notify_new_device(self, user: User) -> None:
        if not user.email:
            return  # зөвхөн утасны бүртгэл: үйл явдал журналд харагдана
        # Дэлгүүрийн цагаар бичнэ: UTC цаг уншиж буй хүний цагаас зөрж, танихгүй нэвтрэлт мэт
        # харагдана.
        when = datetime.now(self._settings.shop_zone).strftime("%Y-%m-%d %H:%M")
        self.queue_notice(
            Email(
                to=user.email,
                subject="Шинэ төхөөрөмжөөс нэвтэрлээ",
                body="Таны бүртгэлд шинэ төхөөрөмжөөс нэвтэрлээ.\n\n"
                f"Төхөөрөмж: {describe_device(self._client.user_agent)}\n"
                f"Цаг: {when}\n\n"
                "Хэрэв та өөрөө биш бол нууц үгээ даруй солиод, «Миний мэдээлэл» хуудасны "
                "«Таны төхөөрөмжүүд» хэсгээс бусад төхөөрөмжийг гаргана уу.",
            )
        )

    @staticmethod
    def _email_taken() -> ProblemError:
        return ProblemError(
            HTTPStatus.CONFLICT,
            "Имэйл бүртгэлтэй байна",
            "Энэ имэйлээр бүртгэл аль хэдийн үүссэн байна. Нэвтэрч үзнэ үү.",
            type_=EMAIL_TAKEN_TYPE,
        )
