"""TOTP (RFC 6238, SHA-1, 6 цифр, 30 секунд): Google Authenticator, 1Password зэрэг ямар ч апп
дэмждэг хэлбэр. Мөн утсаа алдсан үед хэрэглэх нэг удаагийн нөөц код."""

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

import segno

STEP_SECONDS = 30
DIGITS = 6
# Утасны цаг бага зэрэг зөрсөн байж болно: өмнөх ба дараагийн нэг алхмыг зөвшөөрнө.
WINDOW = 1
RECOVERY_CODE_COUNT = 10
# 0/O/1/I байхгүй: нөөц кодыг гараар хуулж бичдэг.
_RECOVERY_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10**DIGITS:0{DIGITS}d}"


def matching_step(secret: str, code: str, at: float, *, after: int | None = None) -> int | None:
    """Код таарсан цагийн алхмыг буцаана, таарахгүй бол None. `after` (өмнө ашигласан) алхам болон
    түүнээс өмнөх алхмын кодыг хүлээн авахгүй. Тиймээс хэн нэгний харж авсан кодыг дахин ашиглах
    боломжгүй."""
    current = int(at // STEP_SECONDS)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if after is not None and step <= after:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "Angel") -> str:
    query = urlencode({"secret": secret, "issuer": issuer}, quote_via=quote)
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?{query}"


def qr_data_uri(uri: str) -> str:
    """Баталгаажуулагч апп-аар уншуулах QR (SVG data URI): web талд нэмэлт сан хэрэггүй, нууц гадны
    үйлчилгээ рүү явахгүй."""
    return str(segno.make(uri, error="m").svg_data_uri(scale=5, border=3, light="#ffffff"))


def new_recovery_codes() -> list[str]:
    def one() -> str:
        text = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{text[:5]}-{text[5:]}"

    return [one() for _ in range(RECOVERY_CODE_COUNT)]


def hash_recovery_code(code: str) -> str:
    normalised = code.strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).hexdigest()
