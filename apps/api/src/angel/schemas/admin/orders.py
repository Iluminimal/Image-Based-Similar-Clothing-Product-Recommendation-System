from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from angel.schemas.commerce.order import (
    OrderEventOut,
    OrderEventType,
    OrderOut,
    OrderRequestOut,
    OrderStatus,
    RequestKind,
    RequestStatus,
    ShippingMethodId,
)

# --- захиалгууд (зөвхөн унших) ---

# `requests`: төлвөөс үл хамааран шийдэгдэж дуусаагүй цуцлах, буцаах хүсэлттэй захиалгууд.
AdminOrderStatusFilter = Literal[
    "all", "requests", "pending", "paid", "shipped", "delivered", "cancelled", "refunded"
]
AdminOrderEventType = OrderEventType | Literal["note"]


class OpenRequestBrief(BaseModel):
    kind: RequestKind
    status: RequestStatus


class AdminOrderListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: Annotated[
        str | None,
        Field(min_length=1, max_length=100, description="Order number or customer email"),
    ] = None
    status: AdminOrderStatusFilter = "all"
    page: Annotated[int, Field(ge=1, le=10_000)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 25


class AdminOrderSummary(BaseModel):
    number: str
    status: OrderStatus
    created_at: datetime
    currency: str
    total_cents: int
    item_count: int
    shipping_method: ShippingMethodId
    customer_email: str
    customer_name: str
    payment_status: str | None
    open_request: OpenRequestBrief | None


class AdminOrderPage(BaseModel):
    items: list[AdminOrderSummary]
    # `q` хайлтад таарах захиалгын төлөв бүрийн тоо (tab-ууд үүнийг харуулна), `status`-аас үл
    # хамаарна.
    status_counts: dict[str, int]
    # Мөн хайлтад таарах, нээлттэй хүсэлттэй захиалга ("Хүсэлт" tab): төлвүүдтэй давхцдаг тул
    # `status_counts`-д ордоггүй.
    open_requests: int
    total: int
    page: int
    page_size: int
    pages: int


class AdminPaymentOut(BaseModel):
    """Төлбөрийн бичлэг. QR зураг гэх мэт provider-ийн өгөгдөл энд гарахгүй. `charge_*` нь бодитоор
    авсан дүн (минор нэгжээр) ба түгжсэн ханш."""

    provider: str
    provider_payment_id: str
    status: str
    amount_cents: int
    currency: str
    charge_currency: str
    charge_minor: int
    last_error: str | None
    refund_id: str | None


class AdminOrderEventOut(OrderEventOut):
    """Ижил алхам, гэхдээ administrator харж болох бүх зүйлтэй: тэмдэглэл, хэн хийсэн."""

    type: AdminOrderEventType  # type: ignore[assignment]
    data: dict[str, Any]


class AdminOrderRequestOut(OrderRequestOut):
    # Буцаж ирсэн барааг агуулах нөөцөд нэмсэн эсэх.
    restocked: bool | None


class AdminOrderOut(OrderOut):
    user_id: int
    cancel_reason: str | None
    cancelled_at: datetime | None
    payment: AdminPaymentOut | None
    events: list[AdminOrderEventOut]  # type: ignore[assignment]
    requests: list[AdminOrderRequestOut]  # type: ignore[assignment]


# --- захиалгын үйлдлүүд ---

Carrier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
TrackingNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ShipRequest(BaseModel):
    """Хүргэлтийн захиалгад хоёулаа заавал. Дэлгүүрээс авах захиалгад хоёуланг нь орхино: энэ
    үйлдэл "авахад бэлэн" гэсэн үг."""

    model_config = ConfigDict(extra="forbid")

    carrier: Carrier | None = None
    tracking_number: TrackingNumber | None = None


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason | None = None


class RefundRequest(BaseModel):
    """Үргэлж бүтэн дүн (төлбөрийн gateway-ийн дэмждэг зүйл)."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason
    # Бараа нөөцөд буцаана: хэзээ ч явагдаагүй захиалгад тийм, аль хэдийн илгээсэнд үгүй.
    restock: bool


CustomerNote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class ApproveOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Хэрэглэгчид харагдана.
    note: CustomerNote | None = None


class DeclineOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Хэрэглэгчид харагдана: шалтгаангүй татгалзахгүй.
    note: CustomerNote


class ReceiveReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Буцаж ирсэн барааг дахин зарах боломжтой бол нөөцөд нэмнэ.
    restock: bool


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
