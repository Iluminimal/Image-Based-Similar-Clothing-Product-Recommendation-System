from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from angel.schemas.accounts.address import AddressSnapshot
from angel.schemas.catalog.product import ProductImage

OrderStatus = Literal["pending", "paid", "shipped", "delivered", "cancelled", "refunded"]
ShippingMethodId = Literal["standard", "express", "pickup"]
ShippingZone = Literal["ub", "rural"]
RequestKind = Literal["cancel", "return"]
RequestStatus = Literal["requested", "approved", "received", "completed", "declined", "withdrawn"]
RequestReason = Literal[
    "changed_mind",
    "wrong_order",
    "too_slow",
    "wrong_size",
    "not_as_described",
    "defective",
    "wrong_item",
    "other",
]
# Хүсэлтийн төрөл бүрд тохирох шалтгаанууд.
REQUEST_REASONS: dict[str, tuple[str, ...]] = {
    "cancel": ("changed_mind", "wrong_order", "too_slow", "other"),
    "return": (
        "wrong_size",
        "not_as_described",
        "defective",
        "wrong_item",
        "changed_mind",
        "other",
    ),
}
OrderEventType = Literal[
    "placed",
    "paid",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
    "cancel_requested",
    "return_requested",
    "request_approved",
    "request_declined",
    "request_withdrawn",
    "return_received",
]


class ShippingMethodOut(BaseModel):
    id: ShippingMethodId
    label: str
    description: str
    price_cents: int
    estimated_days: str


class ShippingMethodList(BaseModel):
    items: list[ShippingMethodOut]
    currency: str
    free_shipping_threshold_cents: int


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_id: Annotated[int, Field(ge=1, le=2**63 - 1)]
    shipping_method: ShippingMethodId
    # Захиалгын имэйлийг очих хаяг. Account-д email байхгүй (утсаар бүртгүүлсэн) үед л заавал; бусад
    # үед account-ын email-ийг хэрэглэнэ.
    contact_email: EmailStr | None = None
    # Худалдан авагчийн дэлгэц дээр харсан нийт дүн. Серверийн тооцсон дүнтэй зөрвөл захиалга
    # үүсгэхгүй (409 price-changed): зөвшөөрөөгүй үнээр захиалга хийхгүй. Web үүнийг үргэлж илгээнэ.
    expected_total_cents: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = None

    @field_validator("contact_email", mode="after")
    @classmethod
    def _lower(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class OrderItemOut(BaseModel):
    product_id: int
    name: str
    slug: str
    image: ProductImage
    size: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


class OrderEventOut(BaseModel):
    """Захиалгын түүхийн нэг алхам, худалдан авагчид харагддаг хэлбэрээр."""

    type: OrderEventType
    at: datetime
    # Зөвхөн харуулахад аюулгүй мэдээлэл: тээвэрлэгч, tracking дугаар, цуцалсан шалтгаан, хүсэлтийн
    # төрөл.
    data: dict[str, Any]


class OrderRequestCreate(BaseModel):
    """Бүтэн захиалгыг цуцлах (илгээгээгүй) эсвэл буцаах (хүргэгдсэн) хүсэлт."""

    model_config = ConfigDict(extra="forbid")

    kind: RequestKind
    reason: RequestReason
    details: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

    @model_validator(mode="after")
    def _reason_fits(self) -> Self:
        if self.reason not in REQUEST_REASONS[self.kind]:
            raise ValueError(f"reason '{self.reason}' does not apply to a {self.kind} request")
        self.details = self.details or None
        if self.reason == "other" and self.details is None:
            raise ValueError("details are required when the reason is 'other'")
        return self


class OrderRequestOut(BaseModel):
    id: int
    kind: RequestKind
    status: RequestStatus
    reason: RequestReason
    details: str | None
    # Ажилтнаас хэрэглэгчид бичсэн тайлбар (татгалзсан бол үргэлж байна).
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None
    received_at: datetime | None
    closed_at: datetime | None


class ChargeOut(BaseModel):
    """Бодитоор авсан (авах) дүн. `amount_minor` нь бага нэгжээр (MNT: төгрөг x 100)."""

    currency: str
    amount_minor: int


class QPayBankOut(BaseModel):
    """Банкны апп-ын холбоос (утсан дээр шууд тухайн апп-ыг нээнэ)."""

    name: str
    description: str
    logo: str
    link: str


class QPayCheckoutOut(BaseModel):
    """QPay нэхэмжлэх: компьютер дээр QR-ыг банкны апп-аар уншуулна, утсан дээр холбоосоор."""

    qr_image: str = Field(description="Base64 PNG of the QR code")
    qr_text: str
    short_url: str
    banks: list[QPayBankOut]


class OrderOut(BaseModel):
    number: str
    status: OrderStatus
    created_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    refunded_at: datetime | None
    carrier: str | None
    tracking_number: str | None
    events: list[OrderEventOut]
    currency: str
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    shipping_method: ShippingMethodId
    shipping_address: AddressSnapshot
    contact_email: str
    items: list[OrderItemOut]
    charge: ChargeOut | None
    # Мөнгийг буцаах ёстой боловч provider хараахан гүйцэтгээгүй (дахин оролдож байна).
    refund_pending: bool = False
    # Цуцлах, буцаах хүсэлтүүд, хуучнаас нь.
    requests: list[OrderRequestOut]
    # Доорх гурав нь худалдан авагчийн захиалгын хуудсанд л бөглөгдөнө. Одоо гаргаж болох хүсэлт:
    available_request: RequestKind | None = None
    # Хүргэгдсэн захиалгыг буцаах хүсэлт гаргах эцсийн хугацаа.
    return_deadline: datetime | None = None
    # Зөвшөөрөгдсөн буцаалтын барааг хүргэж өгөх хаяг.
    return_address: str | None = None
    # Зөвхөн төлбөр хүлээж буй (pending) захиалгад: энэ хугацаанд төлөхгүй бол нөөц буцна. Тэр
    # хүртэл QR-ыг дахин харуулж, төлбөрөө үргэлжлүүлж болно.
    expires_at: datetime | None = None
    qpay: QPayCheckoutOut | None = None


class OrderSummary(BaseModel):
    number: str
    status: OrderStatus
    created_at: datetime
    currency: str
    total_cents: int
    charge: ChargeOut | None
    item_count: int
    shipping_method: ShippingMethodId
    # Эхний хэдэн барааны зураг, түүхийн жагсаалтад.
    images: list[ProductImage]


class OrderPage(BaseModel):
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int
    pages: int


class PaymentOut(BaseModel):
    """Browser-т төлбөр хийхэд хэрэгтэй мэдээлэл. `qpay`: QR болон банкны холбоосыг харуулж, дараа
    нь `check-payment`-аар баталгаажуулна. `offline` (development): simulate endpoint-ийг дуудна."""

    provider: Literal["qpay", "offline"]
    # Захиалга төлбөр үүсгэхээс өмнө цуцлагдсан бол None.
    charge: ChargeOut | None
    qpay: QPayCheckoutOut | None


class PaymentMethodOut(BaseModel):
    """Захиалга үүсэхээс өмнө checkout ямар аргаар төлбөр авахыг мэдэгдэнэ (хуудас зөв алхам
    харуулахын тулд). `provider` None бол төлбөр тохируулаагүй. `charge_currency` бол бодитоор
    авах валют."""

    provider: Literal["qpay", "offline"] | None
    charge_currency: str


class CheckoutOut(BaseModel):
    order: OrderOut
    payment: PaymentOut
