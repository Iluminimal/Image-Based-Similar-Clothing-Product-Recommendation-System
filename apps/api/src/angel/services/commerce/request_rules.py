"""Цуцлах, буцаах хүсэлтийг хэзээ гаргаж болохыг тогтоодог цорын ганц газар: API үүгээр шалгана, web
зөвхөн `available_request`-ийг дагана."""

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
    """Илгээгээгүй, төлөгдсөн захиалгад цуцлах хүсэлт; хүргэгдсэн захиалгад хугацаандаа багтвал
    буцаах хүсэлт. Нэг үед нэг л хүсэлт. Татгалзагдсан бол ижил төрлийн хүсэлтийг дахин гаргахгүй
    (харин өөрөө татаж авсан бол дахин гаргаж болно)."""
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
