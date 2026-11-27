"""Нэвтэрсэн хэрэглэгч өөрийн account дээр хийх үйлдлүүд: нэр, нууц үг, утас, имэйл, төхөөрөмжүүд,
аюулгүй байдлын үйлдлийн түүх, account устгах.

Нууц үг, утас, имэйл өөрчлөх, account устгахын өмнө нууц үг эсвэл шинэ кодоор дахин баталгаажуулна.
Нээлттэй үлдсэн session дангаараа хангалтгүй.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Literal, cast

from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    EMAIL_TAKEN_TYPE,
    FORBIDDEN_TYPE,
    INVALID_CREDENTIALS_TYPE,
    LAST_SIGN_IN_METHOD_TYPE,
    OPEN_ORDERS_TYPE,
    PHONE_TAKEN_TYPE,
    REAUTH_REQUIRED_TYPE,
    UNAUTHENTICATED_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.core.security import hash_password, hash_token, verify_password
from angel.models import Address, Cart, OAuthIdentity, User, WishlistItem
from angel.models import security as events
from angel.repositories.accounts.otp import OtpRepository
from angel.repositories.accounts.security_events import SecurityEventRepository
from angel.repositories.accounts.users import RefreshTokenRepository, UserRepository
from angel.repositories.commerce.order_requests import OrderRequestRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.repositories.system.outbox import OutboxRepository
from angel.schemas.accounts.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    DeviceSession,
    SecurityEventOut,
    SecurityEventType,
)
from angel.services.accounts.auth import (
    AuthService,
    IssuedSession,
    UserView,
    ensure_strong_password,
)
from angel.services.accounts.devices import describe_device, mask_ip
from angel.services.accounts.otp import (
    OtpService,
    normalize_email,
    normalize_phone_number,
)

log = get_logger(__name__)

DELETED_NAME = "Устгасан хэрэглэгч"
# Дэлгүүр монгол хэлтэй болохоос өмнө устгагдсан account-д хадгалсан нэр. Харуулахдаа DELETED_NAME
# болгоно.
LEGACY_DELETED_NAME = "Deleted user"


def _wrong_password() -> ProblemError:
    # 401 биш 403: хэрэглэгч нэвтэрсэн хэвээр. Web апп 401-ийг session дууссан гэж ойлгодог.
    return ProblemError(
        HTTPStatus.FORBIDDEN,
        "Нууц үг буруу",
        "Таны оруулсан нууц үг буруу байна.",
        type_=INVALID_CREDENTIALS_TYPE,
    )


SECURITY_EVENTS_SHOWN = 30


class AccountService:
    """Нэвтэрсэн хүн өөрийн бүртгэлд хийж болох зүйлс: нэр солих, нууц үг тохируулах эсвэл солих,
    устгах."""

    def __init__(
        self, session: AsyncSession, auth: AuthService, otp: OtpService, settings: Settings
    ) -> None:
        self._session = session
        self._auth = auth
        self._otp = otp
        self._settings = settings
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._events = SecurityEventRepository(session)

    async def update_name(self, user_id: int, full_name: str) -> UserView:
        async with self._session.begin():
            user = await self._active_user(user_id)
            user.full_name = full_name
            self._session.add(user)
            return UserView(user, await self._users.providers(user.id))

    async def change_password(self, user_id: int, request: ChangePasswordRequest) -> IssuedSession:
        """Нууц үг тохируулах эсвэл солих. Бусад бүх нэвтрэлт дуусна (нууц үг солих нь хуучныг бусад
        хүн мэдсэн байж болзошгүй гэсэн үг). Энэ browser шинэ session авна."""
        async with self._session.begin():
            user = await self._active_user(user_id)
        # Нууц үгийг эхэлж шалгана: сул нууц үгээс болж баталгаажуулах код дэмий зарцуулагдахгүй.
        ensure_strong_password(request.new_password, email=user.email, full_name=user.full_name)
        await self._confirm_identity(user, request.current_password, request.reauth_code)
        new_hash = await asyncio.to_thread(hash_password, request.new_password)
        async with self._session.begin():
            user = await self._active_user(user_id)
            user.password_hash = new_hash
            self._session.add(user)
            await self._tokens.revoke_all_for_user(user.id, datetime.now(UTC))
            issued = await self._auth.issue_session(user)
            self._auth.record_event(user.id, events.PASSWORD_CHANGED)
            if user.email:
                self._auth.queue_notice(
                    Email(
                        to=user.email,
                        subject="Таны нууц үг солигдлоо",
                        body="Таны нууц үг солигдож, бусад бүх төхөөрөмжөөс таныг гаргалаа. "
                        "Хэрэв та өөрөө солиогүй бол бидэнтэй яаралтай холбогдоно уу.",
                    )
                )
        await self._auth.clear_failures(user.identifier, include_daily=True)
        log.info("password_changed", user_id=user_id, had_password=user.password_hash is not None)
        return issued

    async def delete(self, user_id: int, request: DeleteAccountRequest) -> None:
        """Account-ыг нэргүй болгоно. Захиалгууд үлдэнэ (нягтлан бодох бүртгэлд хэрэгтэй,
        `orders.user_id` нь RESTRICT). Захиалга зөвхөн өөрийн snapshot-ыг хадгална, харин user
        мөрөөс тэр хэн байсныг мэдэх боломжгүй болно."""
        async with self._session.begin():
            user = await self._active_user(user_id)
        if user.is_staff:
            raise ProblemError(
                HTTPStatus.FORBIDDEN,
                "Ажилтны бүртгэлийг эндээс устгах боломжгүй",
                type_=FORBIDDEN_TYPE,
            )
        if request.confirm != user.identifier:
            raise ProblemError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "Баталгаажуулалт таарахгүй байна",
                "Бүртгэлийг устгахын тулд энэ бүртгэлийн имэйл хаяг эсвэл "
                "утасны дугаарыг бичнэ үү.",
            )
        # Кодыг зарцуулахаас өмнө шалгана; доорх transaction дотор түгжээтэйгээр дахин шалгана.
        async with self._session.begin():
            await self._require_no_open_orders(user_id)
        await self._confirm_identity(user, request.password, request.reauth_code)
        async with self._session.begin():
            # Checkout-той ижил түгжээ авна: шалгах, устгах хоёрын хооронд шинэ захиалга үүсэхгүй.
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"checkout:{user_id}"},
            )
            await self._require_no_open_orders(user_id)
            user = await self._active_user(user_id)
            await self._forget_personal_data(user)
            for model in (Address, WishlistItem, Cart, OAuthIdentity):
                await self._session.execute(delete(model).where(model.user_id == user.id))
            await self._tokens.delete_all_for_user(user.id)
            user.email = f"deleted-{user.id}@deleted.invalid"
            user.phone = None
            user.email_verified_at = None
            user.phone_verified_at = None
            user.full_name = DELETED_NAME
            user.password_hash = None
            user.avatar_url = None
            user.is_active = False
            self._session.add(user)
        await self._auth.clear_failures(request.confirm)
        log.info("account_deleted", user_id=user_id)

    async def _forget_personal_data(self, user: User) -> None:
        """Захиалга user мөр рүү заадаг тул мөрийг устгахгүй, тиймээс cascade ажиллахгүй. Тэр хүний
        мэдээлэл агуулсан бусад бичлэгийг энд арилгана. Хаяг солигдохоос өмнө дуудна. Захиалгын
        snapshot (нэр, хаяг, утас, имэйл) санхүүгийн бичиг баримт болж үлдэнэ."""
        orders = OrderRepository(self._session)
        own = [address for address in (user.email, user.phone) if address]
        await OtpRepository(self._session).delete_for_account(user.id, own)
        await self._events.delete_for_user(user.id)
        await OutboxRepository(self._session).forget_finished(
            [*own, *await orders.contact_emails_of(user.id)]
        )
        await OrderRequestRepository(self._session).forget_written_by(user.id)

    # --- төхөөрөмжүүд: нээлттэй нэвтрэлтүүд ---

    async def sessions(self, user_id: int, refresh_token: str | None) -> list[DeviceSession]:
        now = datetime.now(UTC)
        async with self._session.begin():
            current = await self._current_family(user_id, refresh_token)
            rows = await self._tokens.active_sessions(user_id, now)
        return [
            DeviceSession(
                id=token.family_id,
                device=describe_device(token.user_agent),
                ip=token.ip,
                created_at=began,
                last_used_at=token.last_used_at or token.created_at,
                current=token.family_id == current,
            )
            for token, began in rows
        ]

    async def security_events(self, user_id: int) -> list[SecurityEventOut]:
        """Account-ын сүүлийн 30 аюулгүй байдлын үйл явдал: эзэн нь account дээрээ юу болсныг харна.
        IP-ийн сүүлийн хэсгийг нууцална."""
        async with self._session.begin():
            rows = await self._events.recent(user_id, SECURITY_EVENTS_SHOWN)
        return [
            SecurityEventOut(
                id=row.id,
                type=cast(SecurityEventType, row.type),
                method=cast(Literal["password", "otp", "google"] | None, row.method),
                device=describe_device(row.user_agent),
                ip=mask_ip(row.ip),
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def revoke_session(
        self, user_id: int, family_id: uuid.UUID, refresh_token: str | None
    ) -> bool:
        """Нэг нэвтрэлтийг дуусгана. Хүсэлт гаргасан browser-ийн нэвтрэлт бол True."""
        async with self._session.begin():
            current = await self._current_family(user_id, refresh_token)
            ended = await self._tokens.revoke_family_of_user(user_id, family_id, datetime.now(UTC))
            if ended:
                self._auth.record_event(user_id, events.SESSIONS_REVOKED)
        if not ended:
            raise ProblemError(
                HTTPStatus.NOT_FOUND, "Төхөөрөмж олдсонгүй", "Тэр төхөөрөмжөөс аль хэдийн гарсан."
            )
        return family_id == current

    async def revoke_other_sessions(self, user_id: int, refresh_token: str | None) -> None:
        """ "Бусад бүх газраас гарах": энэ browser-оос бусад бүх нэвтрэлт."""
        async with self._session.begin():
            current = await self._current_family(user_id, refresh_token)
            if current is None:
                raise ProblemError(
                    HTTPStatus.UNAUTHORIZED,
                    "Нэвтрээгүй байна",
                    "Дахин нэвтэрнэ үү.",
                    type_=UNAUTHENTICATED_TYPE,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            await self._tokens.revoke_others(user_id, current, datetime.now(UTC))
            self._auth.record_event(user_id, events.SESSIONS_REVOKED)

    async def _current_family(self, user_id: int, refresh_token: str | None) -> uuid.UUID | None:
        if not refresh_token:
            return None
        row = await self._tokens.get_by_hash(hash_token(refresh_token))
        return row.family_id if row is not None and row.user_id == user_id else None

    # --- утасны дугаар ба email: нэмэх, солих, баталгаажуулах, устгах ---

    async def request_phone(
        self, user_id: int, raw_phone: str, password: str | None, reauth_code: str | None = None
    ) -> None:
        """Нэмэх эсвэл солих гэж буй дугаар руу код илгээнэ."""
        phone = normalize_phone_number(raw_phone, self._settings.default_phone_region)
        user = await self._checked_user(user_id, password, reauth_code)
        if user.phone == phone:
            raise _already_yours("утасны дугаар")
        async with self._session.begin():
            if await self._users.get_by_phone(phone) is not None:
                raise _phone_taken()
        await self._otp.issue("change_phone", phone, user_id=user.id)

    async def confirm_phone(self, user_id: int, raw_phone: str, code: str) -> UserView:
        phone = normalize_phone_number(raw_phone, self._settings.default_phone_region)
        await self._otp.verify("change_phone", phone, code, user_id=user_id)
        try:
            async with self._session.begin():
                user = await self._active_user(user_id)
                other = await self._users.get_by_phone(phone)
                if other is not None and other.id != user.id:
                    raise _phone_taken()
                user.phone = phone
                user.phone_verified_at = datetime.now(UTC)
                self._session.add(user)
                await self._session.flush()
                self._auth.record_event(user.id, events.PHONE_CHANGED)
                return UserView(user, await self._users.providers(user.id))
        except IntegrityError:  # шалгалт болон бичилтийн хооронд өөр хүн авчихсан
            raise _phone_taken() from None

    async def remove_phone(
        self, user_id: int, password: str | None, reauth_code: str | None = None
    ) -> UserView:
        user = await self._checked_user(user_id, password, reauth_code)
        async with self._session.begin():
            user = await self._active_user(user_id)
            if user.phone is None:
                return UserView(user, await self._users.providers(user.id))
            if user.email is None:
                raise _last_method("утасны дугаар")
            user.phone = None
            user.phone_verified_at = None
            self._session.add(user)
            return UserView(user, await self._users.providers(user.id))

    async def request_email(
        self, user_id: int, raw_email: str, password: str | None, reauth_code: str | None = None
    ) -> None:
        email = normalize_email(raw_email)
        user = await self._checked_user(user_id, password, reauth_code)
        if user.email == email:
            raise _already_yours("имэйл хаяг")
        async with self._session.begin():
            if await self._users.get_by_email(email) is not None:
                raise _email_taken()
        await self._otp.issue("change_email", email, user_id=user.id)

    async def confirm_email(self, user_id: int, raw_email: str, code: str) -> UserView:
        email = normalize_email(raw_email)
        await self._otp.verify("change_email", email, code, user_id=user_id)
        try:
            async with self._session.begin():
                user = await self._active_user(user_id)
                other = await self._users.get_by_email(email)
                if other is not None and other.id != user.id:
                    raise _email_taken()
                previous = user.email
                user.email = email
                user.email_verified_at = datetime.now(UTC)
                self._session.add(user)
                await self._session.flush()
                self._auth.record_event(user.id, events.EMAIL_CHANGED)
                if previous and previous != email:
                    # Хуучин хаяг руу мэдэгдэнэ: account булаан авсан хүн хаягийг нууцаар сольж
                    # чадахгүй.
                    self._auth.queue_notice(
                        Email(
                            to=previous,
                            subject="Таны бүртгэлийн имэйл хаяг солигдлоо",
                            body="Таны бүртгэлийн имэйл хаяг өөр хаяг болж солигдлоо. "
                            "Хэрэв та өөрөө солиогүй бол бидэнтэй яаралтай холбогдоно уу.",
                        )
                    )
                view = UserView(user, await self._users.providers(user.id))
        except IntegrityError:
            raise _email_taken() from None
        return view

    async def remove_email(
        self, user_id: int, password: str | None, reauth_code: str | None = None
    ) -> UserView:
        user = await self._checked_user(user_id, password, reauth_code)
        async with self._session.begin():
            user = await self._active_user(user_id)
            if user.email is None:
                return UserView(user, await self._users.providers(user.id))
            if user.phone is None:
                raise _last_method("имэйл хаяг")
            # Нууц үгээр нэвтрэхэд email хэрэгтэй. Email-гүй бол нууц үг хэрэггүй ачаа болно.
            user.email = None
            user.email_verified_at = None
            user.password_hash = None
            self._session.add(user)
            return UserView(user, await self._users.providers(user.id))

    async def request_email_verification(self, user_id: int) -> None:
        async with self._session.begin():
            user = await self._active_user(user_id)
        if user.email is None or user.email_verified_at is not None:
            return
        await self._otp.issue("verify_email", user.email, user_id=user.id)

    async def confirm_email_verification(self, user_id: int, code: str) -> UserView:
        async with self._session.begin():
            user = await self._active_user(user_id)
        if user.email is None:
            raise _already_yours("имэйл хаяг")
        await self._otp.verify("verify_email", user.email, code, user_id=user.id)
        async with self._session.begin():
            user = await self._active_user(user_id)
            user.email_verified_at = user.email_verified_at or datetime.now(UTC)
            self._session.add(user)
            return UserView(user, await self._users.providers(user.id))

    # --- туслах функцууд ---

    async def request_reauth(self, user_id: int) -> None:
        """Нууц үггүй бүртгэлийн имэйл (байхгүй бол утас) руу эмзэг үйлдлийг батлах код илгээнэ.
        Нууц үгтэй бүртгэл нууц үгээрээ батална."""
        async with self._session.begin():
            user = await self._active_user(user_id)
        if user.password_hash is None:
            await self._otp.issue("reauth", user.identifier, user_id=user.id)

    async def _checked_user(
        self, user_id: int, password: str | None, reauth_code: str | None
    ) -> User:
        """Нэвтэрсэн бөгөөд дөнгөж сая өөрийгөө дахин баталсан хэрэглэгч."""
        async with self._session.begin():
            user = await self._active_user(user_id)
        await self._confirm_identity(user, password, reauth_code)
        return user

    async def _require_no_open_orders(self, user_id: int) -> None:
        count = await OrderRepository(self._session).count_open_for_user(user_id)
        if count:
            raise ProblemError(
                HTTPStatus.CONFLICT,
                "Дуусаагүй захиалга байна",
                f"Танд дуусаагүй {count} захиалга байна. Хүргэгдсэн эсвэл цуцлагдсаны дараа "
                "бүртгэлээ устгана уу.",
                type_=OPEN_ORDERS_TYPE,
                extensions={"count": count},
            )

    async def _active_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None or not user.is_active:
            raise ProblemError(
                HTTPStatus.UNAUTHORIZED,
                "Нэвтрээгүй байна",
                "Дахин нэвтэрнэ үү.",
                type_=UNAUTHENTICATED_TYPE,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    async def _confirm_identity(
        self, user: User, given: str | None, reauth_code: str | None
    ) -> None:
        """Эмзэг өөрчлөлт хийхэд session дангаараа хангалтгүй: нууц үгтэй бол нууц үг, үгүй бол
        дөнгөж илгээсэн код шаардана. Transaction-оос гадуур дуудна (код өөрийн transaction-тай)."""
        if user.password_hash is None:
            if reauth_code is None:
                raise ProblemError(
                    HTTPStatus.FORBIDDEN,
                    "Өөрийгөө дахин баталгаажуулна уу",
                    "Имэйл эсвэл утсандаа ирэх кодыг оруулна уу.",
                    type_=REAUTH_REQUIRED_TYPE,
                )
            await self._otp.verify("reauth", user.identifier, reauth_code, user_id=user.id)
            return
        rate = await self._auth.check_failure_limit(user.identifier)
        if given is None or not await asyncio.to_thread(verify_password, given, user.password_hash):
            await self._auth.record_failure(user.identifier, rate)
            raise _wrong_password()


def _already_yours(what: str) -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        f"Энэ нь таны одоогийн {what} байна",
        f"Өөр {what} оруулна уу.",
    )


def _phone_taken() -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Утасны дугаар ашиглагдаж байна",
        "Өөр бүртгэл энэ утасны дугаарыг ашиглаж байна.",
        type_=PHONE_TAKEN_TYPE,
    )


def _email_taken() -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Имэйл бүртгэлтэй байна",
        "Өөр бүртгэл энэ имэйл хаягийг ашиглаж байна.",
        type_=EMAIL_TAKEN_TYPE,
    )


def _last_method(what: str) -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Нэвтрэх нэг арга байх ёстой",
        f"{what} хасахын өмнө өөр нэвтрэх арга (имэйл хаяг эсвэл утасны дугаар) нэмнэ үү.",
        type_=LAST_SIGN_IN_METHOD_TYPE,
    )
