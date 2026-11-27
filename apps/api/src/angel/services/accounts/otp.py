"""Нэг удаагийн код: утасны дугаар эсвэл email рүү илгээнэ. Нэг зорилгод, хэдхэн минутын хугацаанд,
цөөн удаагийн оролдлогод хүчинтэй.

Кодын зөвхөн HMAC-ийг хадгална. Бүх алхам database дээр (Redis биш) явдаг тул cache алдагдсан ч
кодыг хууль бусаар ашиглаж нэвтрэхгүй. `issue`, `verify` тус бүр өөрийн transaction-тай: тиймээс
хүсэлт амжилтгүй болсон ч буруу оролдлого тоологдоно."""

import hashlib
import hmac
import math
import secrets
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Literal

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    EMAIL_UNAVAILABLE_TYPE,
    INVALID_DESTINATION_TYPE,
    OTP_EXPIRED_TYPE,
    OTP_INVALID_TYPE,
    OTP_TOO_MANY_ATTEMPTS_TYPE,
    SMS_UNAVAILABLE_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.mail import Email, MailDeliveryError, Mailer
from angel.core.phone import InvalidPhoneError, normalize_phone
from angel.core.rate_limit import RATE_LIMITED_TYPE
from angel.core.sms import Sms, SmsDeliveryError, SmsSender
from angel.repositories.accounts.otp import OtpRepository

log = get_logger(__name__)

OtpPurpose = Literal[
    "login",
    "verify_email",
    "verify_phone",
    "change_email",
    "change_phone",
    "reset_password",
    "reauth",
]

_EMAIL = TypeAdapter(EmailStr)

_SUBJECTS: dict[str, str] = {
    "login": "Таны Angel нэвтрэх код",
    "verify_email": "Angel-д имэйлээ баталгаажуулна уу",
    "verify_phone": "Angel-д утсаа баталгаажуулна уу",
    "change_email": "Angel-д шинэ имэйлээ баталгаажуулна уу",
    "change_phone": "Angel-д шинэ утсаа баталгаажуулна уу",
    "reset_password": "Angel нууц үгээ сэргээх",
    "reauth": "Angel баталгаажуулах код",
}


def is_phone(destination: str) -> bool:
    """Стандарт хэлбэрт оруулсан хүлээн авагч: E.164 дугаар (`+`-ээр эхэлнэ) эсвэл жижиг үсгээр
    бичсэн email."""
    return destination.startswith("+")


def normalize_destination(raw: str, default_region: str) -> str:
    """Хүний бичсэнийг стандарт хэлбэрт оруулна: E.164 дугаар эсвэл жижиг үсгийн email."""
    text = raw.strip()
    try:
        if "@" in text:
            return str(_EMAIL.validate_python(text)).lower()
        return normalize_phone(text, default_region)
    except (ValidationError, InvalidPhoneError):
        raise ProblemError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Утасны дугаар эсвэл имэйл буруу байна",
            "Зөв утасны дугаар эсвэл имэйл хаяг оруулна уу.",
            type_=INVALID_DESTINATION_TYPE,
        ) from None


def normalize_phone_number(raw: str, default_region: str) -> str:
    try:
        return normalize_phone(raw.strip(), default_region)
    except InvalidPhoneError:
        raise ProblemError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Утасны дугаар буруу байна",
            "Зөв утасны дугаар оруулна уу.",
            type_=INVALID_DESTINATION_TYPE,
        ) from None


def normalize_email(raw: str) -> str:
    try:
        return str(_EMAIL.validate_python(raw.strip())).lower()
    except ValidationError:
        raise ProblemError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Имэйл буруу байна",
            "Зөв имэйл хаяг оруулна уу.",
            type_=INVALID_DESTINATION_TYPE,
        ) from None


def invalid_code() -> ProblemError:
    return ProblemError(
        HTTPStatus.BAD_REQUEST,
        "Код буруу байна",
        "Кодоо шалгаад дахин оролдоно уу, эсвэл шинэ код авна уу.",
        type_=OTP_INVALID_TYPE,
    )


class OtpService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        secret: str,
        mailer: Mailer,
        sms: SmsSender,
    ) -> None:
        self._session = session
        self._settings = settings
        self._secret = secret.encode()
        self._mailer = mailer
        self._sms = sms
        self._otps = OtpRepository(session)

    async def issue(
        self,
        purpose: OtpPurpose,
        destination: str,
        *,
        user_id: int | None = None,
        deliver: bool = True,
    ) -> None:
        """Код үүсгээд илгээнэ. `deliver=False` бол challenge-ийг бүртгэх ч юу ч илгээхгүй.
        Бүртгэлгүй хаяг дээрх "нууц үгээ мартсан"-д хэрэглэнэ: энэ нь бүртгэлтэй хаягийнхтай яг
        ижил харагдах ёстой."""
        now = datetime.now(UTC)
        code = self._settings.otp_dev_code or f"{secrets.randbelow(10**6):06d}"
        resend = self._settings.otp_resend_seconds
        async with self._session.begin():
            last = await self._otps.latest(purpose, destination)
            if last is not None:
                # created_at бол database-ийн цаг. Насны бага зэргийн сөрөг утга зөвхөн хоёр цагийн
                # зөрүү.
                age = max(0.0, (now - last.created_at).total_seconds())
                wait = math.ceil(resend - age)
                if wait > 0:
                    raise _too_soon(wait)
            recent = await self._otps.count_since(destination, now - timedelta(hours=1))
            if recent >= self._settings.otp_max_sends_per_hour:
                raise _too_soon(
                    3600, "Энэ хаяг руу хэт олон код илгээсэн байна. Дараа дахин оролдоно уу."
                )
            await self._otps.consume_open(purpose, destination, now)
            await self._otps.add(
                purpose=purpose,
                destination=destination,
                user_id=user_id,
                code_hash=self._hash(purpose, destination, code),
                expires_at=now + timedelta(seconds=self._settings.otp_ttl_seconds),
            )
        if deliver:
            await self._deliver(purpose, destination, code)

    async def verify(
        self,
        purpose: OtpPurpose,
        destination: str,
        code: str,
        *,
        user_id: int | None = None,
    ) -> int | None:
        """Кодыг шалгаад ашигласан болгоно. Challenge-ийг хэнд олгосон user id-г буцаана (login,
        reset үед None). `user_id` өгвөл challenge тэр нэвтэрсэн хэрэглэгчийнх мөн эсэхийг
        шалгана."""
        now = datetime.now(UTC)
        failure: ProblemError | None = None
        owner: int | None = None
        async with self._session.begin():
            row = await self._otps.latest_open_for_update(purpose, destination)
            if row is None:
                failure = invalid_code()
            elif row.expires_at <= now:
                row.consumed_at = now
                failure = ProblemError(
                    HTTPStatus.BAD_REQUEST,
                    "Кодын хугацаа дууссан",
                    "Шинэ код авна уу.",
                    type_=OTP_EXPIRED_TYPE,
                )
            elif user_id is not None and row.user_id != user_id:
                failure = invalid_code()
            elif not hmac.compare_digest(row.code_hash, self._hash(purpose, destination, code)):
                row.attempts += 1
                if row.attempts >= self._settings.otp_max_attempts:
                    row.consumed_at = now
                    failure = _too_many_attempts()
                else:
                    failure = invalid_code()
            else:
                row.consumed_at = now
                owner = row.user_id
        # Алдааг блокийн дараа шиднэ: ингэснээр тоологдсон оролдлого commit хийгдсэн байна.
        if failure is not None:
            log.info("otp_rejected", purpose=purpose, reason=failure.type)
            raise failure
        return owner

    # --- туслах функцууд ---

    def _hash(self, purpose: str, destination: str, code: str) -> str:
        message = f"{purpose}\x00{destination}\x00{code}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    async def _deliver(self, purpose: OtpPurpose, destination: str, code: str) -> None:
        minutes = max(1, self._settings.otp_ttl_seconds // 60)
        if is_phone(destination):
            body = f"{code} - Angel баталгаажуулах код. {minutes} минут хүчинтэй. Хэнд ч бүү өг."
            try:
                await self._sms.send(Sms(to=destination, body=body))
            except SmsDeliveryError:
                raise ProblemError(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "Мессеж илгээж чадсангүй",
                    "Хэсэг хүлээгээд дахин оролдоно уу.",
                    type_=SMS_UNAVAILABLE_TYPE,
                ) from None
            return
        try:
            await self._mailer.send(
                Email(
                    to=destination,
                    subject=_SUBJECTS[purpose],
                    body=(
                        f"Таны код: {code}. {minutes} минут хүчинтэй.\n"
                        "Хэрэв та код хүсээгүй бол энэ имэйлийг тоохгүй байж болно."
                    ),
                )
            )
        except MailDeliveryError:
            raise ProblemError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Имэйл илгээж чадсангүй",
                "Хэсэг хүлээгээд дахин оролдоно уу.",
                type_=EMAIL_UNAVAILABLE_TYPE,
            ) from None


def _too_soon(seconds: int, detail: str | None = None) -> ProblemError:
    return ProblemError(
        HTTPStatus.TOO_MANY_REQUESTS,
        "Шинэ код авахаас өмнө хүлээнэ үү",
        detail or f"{seconds} секундын дараа шинэ код авч болно.",
        type_=RATE_LIMITED_TYPE,
        headers={"Retry-After": str(seconds)},
    )


def _too_many_attempts() -> ProblemError:
    return ProblemError(
        HTTPStatus.TOO_MANY_REQUESTS,
        "Олон удаа буруу код оруулсан",
        "Шинэ код авна уу.",
        type_=OTP_TOO_MANY_ATTEMPTS_TYPE,
    )
