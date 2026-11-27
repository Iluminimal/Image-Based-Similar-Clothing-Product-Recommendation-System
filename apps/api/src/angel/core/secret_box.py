"""Дараа нь буцааж унших шаардлагатай нууцыг (TOTP secret) шифрлэж database-д хадгална. Ингэснээр
database-ийн хуулбар дангаараа 2FA-г тойрох боломж өгөхгүй. Шифрийн түлхүүрийг `JWT_SECRET`-ээс
тусгай нэрээр гаргаж авдаг. Тиймээс `JWT_SECRET`-ийг солих бол ажилтнууд 2FA-гаа дахин
тохируулна."""

import base64
import hashlib
import hmac
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12


def _key(master: str) -> bytes:
    return hmac.new(master.encode(), b"angel:totp-secret:v1", hashlib.sha256).digest()


def seal(master: str, plaintext: str) -> str:
    nonce = secrets.token_bytes(_NONCE_BYTES)
    sealed = AESGCM(_key(master)).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode()


def unseal(master: str, token: str) -> str | None:
    """Эх бичвэрийг буцаана. Түлхүүр солигдсон эсвэл утга эвдэрсэн бол None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        opened = AESGCM(_key(master)).decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], None)
    except (ValueError, InvalidTag):
        return None
    return opened.decode()
