"""Цуцлах, буцаах хүсэлтийг хэзээ гаргаж болохыг тодорхойлох цорын ганц газар: API шалгадаг ба
web `available_request`-ийг л дагадаг."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from angel.models import Order, OrderRequest
from angel.schemas.commerce.order import RequestKind


@dataclass(frozen=True)
class ReturnPolicy:
    window_days: int
    # Буцаах барааг хүргэж өгөх хаяг.
    address: str


def return_deadline(order: Order, window_days: int) -> datetime | None:
    """Дэлгүүрээс авах захиалгад `delivered_at` нь авсан цаг."""
    if order.delivered_at is None:
        return None
    return order.delivered_at + timedelta(days=window_days)


def available_request(
    order: Order, requests: Sequence[OrderRequest], *, now: datetime, window_days: int
) -> RequestKind | None:
    """Илгээгээгүй төлсөн захиалгыг цуцлах, хүргэгдсэн захиалгыг хугацаанд нь буцаах хүсэлт.
    Нэг зэрэг нэг л хүсэлт; татгалзсан бол ижил төрлийнхийг дахин гаргахгүй (өөрөө татаж
    авсны дараа болно)."""
    if any(request.is_open for request in requests):
        return None
    kind: RequestKind
    if order.status == "paid":
        kind = "cancel"
    elif order.status == "delivered":
        deadline = return_deadline(order, window_days)
        if deadline is None or now > deadline:
            return None
        kind = "return"
    else:
        return None
    if any(r.kind == kind and r.status == "declined" for r in requests):
        return None
    return kind
