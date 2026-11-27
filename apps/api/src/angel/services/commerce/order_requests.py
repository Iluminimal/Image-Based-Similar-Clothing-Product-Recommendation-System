"""Худалдан авагчийн цуцлах, буцаах хүсэлт: гаргах, татаж авах. Шийдвэрийг ажилтан
`OrderFulfillmentService`-ээр гаргана."""

from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    INVALID_TRANSITION_TYPE,
    ORDER_NOT_FOUND_TYPE,
    REQUEST_NOT_ALLOWED_TYPE,
    REQUEST_OPEN_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.models import Order, OrderRequest
from angel.repositories.commerce.order_requests import OrderRequestRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.schemas.commerce.order import OrderOut, OrderRequestCreate
from angel.services.commerce.order_text import request_received
from angel.services.commerce.orders import OrderService
from angel.services.commerce.request_rules import available_request
from angel.services.system.outbox import queue_email

log = get_logger(__name__)


class OrderRequestService:
    def __init__(self, session: AsyncSession, settings: Settings, orders: OrderService) -> None:
        self._session = session
        self._settings = settings
        self._view = orders
        self._orders = OrderRepository(session)
        self._requests = OrderRequestRepository(session)

    async def create(self, user_id: int, number: str, data: OrderRequestCreate) -> OrderOut:
        async with self._session.begin():
            # Account устгахтай ижил түгжээ авна: "нээлттэй хүсэлтгүй" гэж шалгасны дараа шинэ
            # хүсэлт үүсэхгүй.
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"checkout:{user_id}"},
            )
            order = await self._lock_own(user_id, number)
            if any(request.is_open for request in order.requests):
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Шийдэгдээгүй хүсэлт байна",
                    "Энэ захиалгад хүлээгдэж буй хүсэлт аль хэдийн бий.",
                    type_=REQUEST_OPEN_TYPE,
                )
            allowed = available_request(
                order,
                order.requests,
                now=datetime.now(UTC),
                window_days=self._settings.return_window_days,
            )
            if allowed != data.kind:
                raise _not_allowed(data.kind, self._settings.return_window_days)
            self._requests.add(
                OrderRequest(
                    order_id=order.id,
                    kind=data.kind,
                    status="requested",
                    reason=data.reason,
                    details=data.details,
                )
            )
            self._orders.add_event(
                order.id, f"{data.kind}_requested", {"reason": data.reason}, user_id
            )
            email = request_received(order, data.kind)
            queue_email(self._session, email)
        log.info("order_request_created", order=number, kind=data.kind, user_id=user_id)
        return await self._view.get(user_id, number)

    async def withdraw(self, user_id: int, number: str, request_id: int) -> OrderOut:
        async with self._session.begin():
            order = await self._lock_own(user_id, number)
            request = next((r for r in order.requests if r.id == request_id), None)
            if request is None or request.status != "requested":
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Хүсэлтийг татах боломжгүй",
                    "Зөвхөн хараахан шийдэгдээгүй хүсэлтийг татаж авч болно.",
                    type_=INVALID_TRANSITION_TYPE,
                )
            request.status = "withdrawn"
            request.closed_at = datetime.now(UTC)
            self._orders.add_event(order.id, "request_withdrawn", {"kind": request.kind}, user_id)
        log.info("order_request_withdrawn", order=number, user_id=user_id)
        return await self._view.get(user_id, number)

    async def _lock_own(self, user_id: int, number: str) -> Order:
        found = await self._orders.get_for_user(user_id, number)
        order = await self._orders.get_for_update(found.id) if found else None
        if order is None:
            # Өөр хүний дугаар ч ижил хариу авна.
            raise ProblemError(
                HTTPStatus.NOT_FOUND,
                "Захиалга олдсонгүй",
                f"Таны бүртгэлд {number} дугаартай захиалга байхгүй байна.",
                type_=ORDER_NOT_FOUND_TYPE,
            )
        return order


def _not_allowed(kind: str, window_days: int) -> ProblemError:
    detail = (
        "Зөвхөн илгээгээгүй, төлсөн захиалгыг цуцлах хүсэлт гаргана."
        if kind == "cancel"
        else f"Хүргэгдсэнээс хойш {window_days} хоногийн дотор буцаах хүсэлт гаргана."
    )
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Энэ захиалгад хүсэлт гаргах боломжгүй",
        f"{detail} Татгалзсан хүсэлтийг дахин гаргах боломжгүй.",
        type_=REQUEST_NOT_ALLOWED_TYPE,
    )
