"""Түлхүүр, сүлжээ шаардахгүй хиймэл төлбөр (хөгжүүлэлт, тестэд)."""

import secrets
from typing import Literal

from angel.payments.gateway import IntentInfo, PaymentEvent, PaymentMode


class OfflineGateway:
    """Provider-гүйгээр хөгжүүлэх (`PAYMENTS_MODE=offline`), тестлэхэд хэрэглэнэ.

    Гадагш ямар ч хүсэлт явуулахгүй: төлбөр зохиомол, худалдан авагч simulate endpoint-оор "төлнө".
    Ингэхэд жинхэнэ provider-тэй адил settlement код ажиллана. Мөнгийг дэлгүүрийн валютаар
    (төгрөгөөр) авна. Production-д хэзээ ч зөвшөөрөхгүй (`Settings`-ийг үзнэ үү).
    """

    mode: PaymentMode = "offline"
    charge_currency: str | None = None

    async def create_intent(
        self, *, amount: int, currency: str, order_number: str, idempotency_key: str
    ) -> IntentInfo:
        # Id-г key-ээс гаргадаг тул давтагдсан хүсэлтэд ижил төлбөр гарна.
        suffix = idempotency_key.replace("-", "")[:24] or secrets.token_hex(12)
        return IntentInfo(f"pay_offline_{suffix}", "requires_payment")

    async def check(self, intent_id: str) -> PaymentEvent | None:
        # Offline горимд төлбөр зөвхөн simulate endpoint-оор орно.
        return None

    async def cancel_intent(self, intent_id: str) -> Literal["canceled", "succeeded"]:
        return "canceled"

    async def refund(self, intent_id: str, *, idempotency_key: str) -> str:
        return f"re_offline_{idempotency_key[:24]}"
