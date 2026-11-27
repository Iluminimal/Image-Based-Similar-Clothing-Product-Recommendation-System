"""Дэлгүүрт төлбөрийн provider-оос хэрэгтэй үйлдлүүд. Тодорхой нэг provider-оос хамаарахгүй.

Service-үүд зөвхөн энэ protocol-ыг мэднэ. `QPayGateway` QPay-тэй харилцана. `OfflineGateway` бол
QPay-ийн түлхүүргүйгээр хөгжүүлэх, тестлэхэд зориулсан хиймэл хувилбар.

Бүх мөнгөн дүн тухайн валютын бага нэгжээр, бүхэл тоогоор (MNT: төгрөг x 100).
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

PaymentMode = Literal["qpay", "offline"]


class PaymentProviderError(Exception):
    """Provider-тэй холбогдож чадсангүй, эсвэл provider хүсэлтийг татгалзсан. Дахин оролдоход
    аюулгүй."""


@dataclass(frozen=True)
class IntentInfo:
    """Provider дээр үүссэн нэг төлбөр (QPay-д нэхэмжлэх). `checkout` нь browser-т төлөхөд
    хэрэгтэй зүйл (QPay: QR зураг, банкны апп-ын холбоос); offline-д хоосон."""

    id: str
    status: str
    checkout: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentEvent:
    """Provider дээр баталгаажсан төлбөр. `amount`, `currency` бол provider-ийн бодитоор авсан дүн
    (бага нэгжээр). Settlement үүнийг төлбөрт урьдаас тогтоосон дүнтэй тулгана."""

    id: str
    intent_id: str
    amount: int
    currency: str
    kind: Literal["succeeded"] = "succeeded"


class PaymentGateway(Protocol):
    mode: PaymentMode
    # Provider ямар валютаар мөнгө авдаг вэ (QPay: зөвхөн MNT). None бол дэлгүүрийн үндсэн валют.
    charge_currency: str | None

    async def create_intent(
        self, *, amount: int, currency: str, order_number: str, idempotency_key: str
    ) -> IntentInfo:
        """Нэг захиалгын төлбөрийг үүсгэнэ (`idempotency_key` давтагдвал өмнөхийг нь буцаана)."""
        ...

    async def check(self, intent_id: str) -> PaymentEvent | None:
        """Provider-оос төлбөрийн төлвийг асууна. Төлөгдсөн бол event, үгүй бол None."""
        ...

    async def cancel_intent(self, intent_id: str) -> Literal["canceled", "succeeded"]:
        """Төлөгдөөгүй төлбөрийг цуцална. "succeeded" буцаавал цуцлахаас өмнө аль хэдийн төлөгдсөн
        гэсэн үг."""
        ...

    async def refund(self, intent_id: str, *, idempotency_key: str) -> str:
        """Төлөгдсөн төлбөрийг бүтнээр нь буцаана; refund id өгнө."""
        ...
