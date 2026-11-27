"""Захиалгын төлөв яаж өөрчлөгдөх вэ (жижиг state machine):

    pending --cancel--> cancelled
    pending --(payment)--> paid --ship--> shipped --deliver--> delivered
    paid | shipped | delivered --refund--> refunded

Худалдан авагчийн хүсэлт (`OrderRequest`): цуцлах хүсэлтийг зөвшөөрвөл төлбөрийг шууд буцаана.
Буцаах хүсэлтийг админ зөвшөөрч, агуулах барааг хүлээн авч, дараа нь админ төлбөрийг буцаана.
Нээлттэй хүсэлттэй захиалгыг илгээхгүй. Төлбөр буцаахад нээлттэй хүсэлт хаагдана.

Үйлдэл бүр захиалгын мөрийг түгжинэ, ингэснээр хоёр админ, эсвэл админ ба webhook дараалж ажиллана.
Дараа нь захиалгын төлөв тухайн үйлдэлд тохирохыг шалгаад (үгүй бол 409) өөрчилнө. Нэг transaction
дотор `OrderEvent` бичиж, хэрэглэгчид очих имэйлийг outbox дараалалд оруулна."""

from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.errors import (
    INVALID_TRANSITION_TYPE,
    ORDER_NOT_FOUND_TYPE,
    PAYMENT_PROVIDER_TYPE,
    PAYMENTS_UNAVAILABLE_TYPE,
    REQUEST_OPEN_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.models import Order, OrderRequest, Product, User
from angel.payments import PaymentGateway
from angel.payments.gateway import PaymentProviderError
from angel.repositories.admin.audit import AuditRepository
from angel.repositories.catalog.products import ProductRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.schemas.admin.orders import (
    AdminOrderOut,
    ApproveOrderRequest,
    CancelRequest,
    DeclineOrderRequest,
    NoteRequest,
    ReceiveReturnRequest,
    RefundRequest,
    ShipRequest,
)
from angel.services.commerce.order_lifecycle import release_order
from angel.services.commerce.order_text import (
    ready_for_pickup_body,
    refund_sent,
    request_declined,
    return_approved,
    return_received,
)
from angel.services.commerce.payments import PaymentSettlement
from angel.services.mappers import to_admin_order_out
from angel.services.system.outbox import queue_email
from angel.storage import Storage

log = get_logger(__name__)

# Цуцлах хүсэлтийг зөвшөөрч мөнгө буцаасны шалтгааны код (захиалгын түүх, журналд хадгална). Web
# үүнийг хэрэглэгчийн хэлээр харуулна.
_CANCEL_APPROVED_REASON = "cancel_request"


class OrderFulfillmentService:
    def __init__(
        self,
        session: AsyncSession,
        gateway: PaymentGateway | None,
        storage: Storage,
        settlement: PaymentSettlement | None = None,
        pickup_address: str = "",
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._storage = storage
        self._settlement = settlement
        self._pickup_address = pickup_address
        self._orders = OrderRepository(session)
        self._audit = AuditRepository(session)

    # --- үйлдлүүд ---

    async def ship(self, number: str, admin: User, request: ShipRequest) -> AdminOrderOut:
        """Хүргэлтийн захиалгыг тээвэрлэгчид өгнө; дэлгүүрээс авах захиалгыг "авахад бэлэн"
        болгоно (тээвэрлэгчгүй)."""
        async with self._session.begin():
            order = await self._lock(number)
            self._require(order, ("paid",), "ship")
            if any(r.is_open for r in order.requests):
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Захиалгыг одоо илгээж болохгүй",
                    "Хэрэглэгч цуцлах хүсэлт гаргасан. Админ шийдтэл хүлээнэ үү.",
                    type_=REQUEST_OPEN_TYPE,
                )
            pickup = order.shipping_method == "pickup"
            _check_shipment_details(pickup, request)
            await self._lock_products(order)
            order.status = "shipped"
            order.carrier = request.carrier
            order.tracking_number = request.tracking_number
            order.shipped_at = datetime.now(UTC)
            details: dict[str, object] = (
                {}
                if pickup
                else {"carrier": request.carrier, "tracking_number": request.tracking_number}
            )
            self._orders.add_event(order.id, "shipped", {**details, **_by(admin)}, admin.id)
            self._audit.record(admin, "order.ship", "order", number, details)
            email = (
                Email(
                    to=order.contact_email,
                    subject=f"{order.number} дугаартай захиалга авахад бэлэн боллоо",
                    body=ready_for_pickup_body(order, self._pickup_address),
                )
                if pickup
                else Email(
                    to=order.contact_email,
                    subject=f"{order.number} дугаартай захиалга замдаа гарлаа",
                    body=f"Таны {order.number} дугаартай захиалгыг илгээлээ.\n\n"
                    f"Тээвэрлэгч: {request.carrier}\n"
                    f"Илгээмжийн дугаар: {request.tracking_number}",
                )
            )
            queue_email(self._session, email)
        log.info("order_shipped", order=number, admin_id=admin.id, pickup=pickup)
        return await self._read(number)

    async def deliver(self, number: str, admin: User) -> AdminOrderOut:
        async with self._session.begin():
            order = await self._lock(number)
            self._require(order, ("shipped",), "mark as delivered")
            order.status = "delivered"
            order.delivered_at = datetime.now(UTC)
            self._orders.add_event(order.id, "delivered", _by(admin), admin.id)
            self._audit.record(admin, "order.deliver", "order", number)
            pickup = order.shipping_method == "pickup"
            arrived = (
                f"Та {order.number} дугаартай захиалгаа авлаа."
                if pickup
                else f"Таны {order.number} дугаартай захиалга хүргэгдлээ."
            )
            subject = (
                f"Та {order.number} дугаартай захиалгаа авлаа"
                if pickup
                else f"{order.number} дугаартай захиалга хүргэгдлээ"
            )
            email = Email(
                to=order.contact_email,
                subject=subject,
                body=f"{arrived} Танд таалагдана гэж найдаж байна!",
            )
            queue_email(self._session, email)
        log.info("order_delivered", order=number, admin_id=admin.id)
        return await self._read(number)

    async def cancel(self, number: str, admin: User, request: CancelRequest) -> AdminOrderOut:
        """Төлөгдөөгүй захиалгыг цуцалж, нөөцийг буцаана. Эхлээд provider дээрх payment intent-ийг
        цуцална (expiry sweeper-тэй адил)."""
        async with self._session.begin():
            order = await self._lock_plain(number)
            self._require(order, ("pending",), "cancel")
            intent_id = order.payment.provider_payment_id if order.payment else None
        if intent_id is not None and self._gateway is not None:
            try:
                outcome = await self._gateway.cancel_intent(intent_id)
            except PaymentProviderError as exc:
                raise _provider_error(exc) from exc
            if outcome == "succeeded":
                if self._settlement is not None:
                    await self._settlement.reconcile(intent_id)
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Захиалга дөнгөж төлөгдлөө",
                    "Төлбөр хэсэг хугацааны өмнө хийгдсэн. Захиалгаа шинэчилж харна уу.",
                    type_=INVALID_TRANSITION_TYPE,
                )
        async with self._session.begin():
            order = await self._lock(number)
            data_user = (admin.id, admin.identifier)
            if not await release_order(self._session, order, "admin", actor=data_user):
                raise _conflict(order, "cancel")
            if request.reason:
                await self._annotate_last_event(order, request.reason)
            self._audit.record(
                admin, "order.cancel", "order", number, {"reason": request.reason or None}
            )
            email = Email(
                to=order.contact_email,
                subject=f"{order.number} дугаартай захиалга цуцлагдлаа",
                body=f"{order.number} дугаартай захиалга цуцлагдлаа. Танаас мөнгө аваагүй.",
            )
            queue_email(self._session, email)
        log.info("order_cancelled_by_admin", order=number, admin_id=admin.id)
        return await self._read(number)

    async def refund(self, number: str, admin: User, request: RefundRequest) -> AdminOrderOut:
        """Төлбөрийг бүтнээр нь буцаана. Нээлттэй хүсэлт байвал хамт хаагдана."""
        async with self._session.begin():
            order = await self._lock(number)
            email = await self._refund_locked(
                order, admin, reason=request.reason, restock=request.restock
            )
            queue_email(self._session, email)
        log.info("order_refunded", order=number, admin_id=admin.id, restock=request.restock)
        return await self._read(number)

    # --- худалдан авагчийн хүсэлтүүд ---

    async def approve_request(
        self, number: str, request_id: int, admin: User, decision: ApproveOrderRequest
    ) -> AdminOrderOut:
        """Цуцлах: бараа хараахан илгээгдээгүй тул төлбөрийг шууд буцааж, барааг үлдэгдэлд
        нэмнэ. Буцаах: барааг хүлээн авсны дараа төлбөрийг буцаана."""
        async with self._session.begin():
            order = await self._lock(number)
            asked = self._request(order, request_id, ("requested",))
            asked.decided_at = datetime.now(UTC)
            asked.decision_note = decision.note
            self._record_decision(order, admin, asked, "approve", "request_approved")
            if asked.kind == "cancel":
                await self._refund_locked(
                    order, admin, reason=_CANCEL_APPROVED_REASON, restock=True
                )
                email = refund_sent(order, decision.note)
            else:
                asked.status = "approved"
                email = return_approved(order, self._pickup_address, decision.note)
            queue_email(self._session, email)
        log.info("order_request_approved", order=number, kind=asked.kind, admin_id=admin.id)
        return await self._read(number)

    async def decline_request(
        self, number: str, request_id: int, admin: User, decision: DeclineOrderRequest
    ) -> AdminOrderOut:
        """Зөвшөөрсөн буцаалтыг ч хааж болно (бараа ирээгүй). Хүлээн авсны дараа болохгүй."""
        async with self._session.begin():
            order = await self._lock(number)
            asked = self._request(order, request_id, ("requested", "approved"))
            now = datetime.now(UTC)
            asked.status = "declined"
            asked.decision_note = decision.note
            asked.decided_at = now
            asked.closed_at = now
            self._record_decision(order, admin, asked, "decline", "request_declined")
            email = request_declined(order, asked.kind, decision.note)
            queue_email(self._session, email)
        log.info("order_request_declined", order=number, kind=asked.kind, admin_id=admin.id)
        return await self._read(number)

    async def receive_return(
        self, number: str, request_id: int, worker: User, receipt: ReceiveReturnRequest
    ) -> AdminOrderOut:
        async with self._session.begin():
            order = await self._lock(number)
            asked = self._request(order, request_id, ("approved",))
            if asked.kind != "return":
                raise _request_conflict()
            products = await self._lock_products(order)
            if receipt.restock:
                self._restock(order, products)
            asked.status = "received"
            asked.received_at = datetime.now(UTC)
            asked.restocked = receipt.restock
            details = {"restock": receipt.restock}
            self._orders.add_event(
                order.id, "return_received", {**details, **_by(worker)}, worker.id
            )
            self._audit.record(worker, "order.receive", "order", number, details)
            email = return_received(order)
            queue_email(self._session, email)
        log.info("order_return_received", order=number, worker_id=worker.id, **details)
        return await self._read(number)

    async def _refund_locked(
        self, order: Order, admin: User, *, reason: str, restock: bool
    ) -> Email:
        """Түгжсэн захиалгын төлбөрийг буцаана. Provider-ийг transaction дотор дууддаг: амжилтгүй
        бол юу ч өөрчлөгдөхгүй, idempotency key-тэй тул давтахад аюулгүй. Буцаалтын имэйлийг
        дуудсан код ижил transaction дотор дараалалд оруулна."""
        if self._gateway is None:
            raise ProblemError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Төлбөр боломжгүй байна",
                "Төлбөрийн үйлчилгээ тохируулагдаагүй тул төлбөрийг буцаах боломжгүй.",
                type_=PAYMENTS_UNAVAILABLE_TYPE,
            )
        self._require(order, ("paid", "shipped", "delivered"), "refund")
        payment = order.payment
        if payment is None or payment.status != "succeeded":
            raise _conflict(order, "refund")
        asked = next((r for r in order.requests if r.is_open), None)
        if restock and asked is not None and asked.status == "received":
            raise ProblemError(
                HTTPStatus.CONFLICT,
                "Үлдэгдлийг аль хэдийн шийдсэн",
                "Буцаасан барааг хүлээн авахдаа агуулахын ажилтан үлдэгдэлд нэмэх эсэхийг "
                "шийдсэн. Үлдэгдэлд дахин нэмэхгүйгээр төлбөрийг буцаана уу.",
                type_=INVALID_TRANSITION_TYPE,
            )
        try:
            payment.refund_id = await self._gateway.refund(
                payment.provider_payment_id,
                idempotency_key=f"refund-{payment.provider_payment_id}",
            )
        except PaymentProviderError as exc:
            raise _provider_error(exc) from exc
        payment.status = "refunded"
        payment.provider_data = None
        payment.last_error = "admin_refund"
        # Төлөв өөрчлөгдөхөд захиалагдсан барааны тоо өөрчлөгддөг. Тиймээс барааг үлдэгдэлд нэмэхгүй
        # байсан ч мөрийг нь түгжинэ.
        products = await self._lock_products(order)
        if restock:
            self._restock(order, products)
        now = datetime.now(UTC)
        order.status = "refunded"
        order.refunded_at = now
        if asked is not None:
            asked.status = "completed"
            asked.decided_at = asked.decided_at or now
            asked.closed_at = now
        details: dict[str, object] = {
            "reason": reason,
            "restock": restock,
            "amount_cents": payment.amount_cents,
        }
        self._orders.add_event(order.id, "refunded", {**details, **_by(admin)}, admin.id)
        self._audit.record(admin, "order.refund", "order", order.number, details)
        return refund_sent(order)

    async def add_note(self, number: str, admin: User, request: NoteRequest) -> AdminOrderOut:
        """Аль ч захиалга дээрх дотоод тэмдэглэл. Хэрэглэгч хэзээ ч харахгүй."""
        async with self._session.begin():
            order_id = await self._orders.id_for_number(number)
            if order_id is None:
                raise _not_found(number)
            self._orders.add_event(order_id, "note", {"text": request.text, **_by(admin)}, admin.id)
            self._audit.record(admin, "order.note", "order", number)
        return await self._read(number)

    # --- туслах функцууд ---

    async def _lock(self, number: str) -> Order:
        order_id = await self._orders.id_for_number(number)
        order = await self._orders.get_for_update(order_id) if order_id is not None else None
        if order is None:
            raise _not_found(number)
        return order

    async def _lock_plain(self, number: str) -> Order:
        order = await self._orders.get_by_number(number)
        if order is None:
            raise _not_found(number)
        return order

    @staticmethod
    def _require(order: Order, allowed: tuple[str, ...], action: str) -> None:
        if order.status not in allowed:
            raise _conflict(order, action)

    @staticmethod
    def _request(order: Order, request_id: int, allowed: tuple[str, ...]) -> OrderRequest:
        """Хуучирсан дэлгэцээс өөр хүсэлт дээр шийдвэр гаргахаас сэргийлж хүсэлтийг id-аар нь
        сонгоно."""
        asked = next((r for r in order.requests if r.id == request_id), None)
        if asked is None or asked.status not in allowed:
            raise _request_conflict()
        return asked

    def _record_decision(
        self, order: Order, admin: User, asked: OrderRequest, action: str, event: str
    ) -> None:
        data: dict[str, object] = {"kind": asked.kind, "note": asked.decision_note}
        self._orders.add_event(order.id, event, {**data, **_by(admin)}, admin.id)
        self._audit.record(admin, f"order.{action}", "order", order.number, data)

    async def _lock_products(self, order: Order) -> dict[int, Product]:
        """Захиалгын барааны мөрүүдийг түгжинэ (checkout-той адил id-ийн дарааллаар, deadlock-гүй).
        Захиалагдсан тоог өөрчилдөг үйлдэл тооллоготой давхцахгүй, ээлжлэн явна."""
        ids = sorted({item.product_id for item in order.items})
        return await ProductRepository(self._session).get_many(ids, for_update=True)

    @staticmethod
    def _restock(order: Order, products: dict[int, Product]) -> None:
        for item in order.items:
            products[item.product_id].stock_quantity += item.quantity

    async def _annotate_last_event(self, order: Order, note: str) -> None:
        await self._session.flush()
        self._orders.add_event(order.id, "note", {"text": f"Cancelled: {note}"})

    async def _read(self, number: str) -> AdminOrderOut:
        async with self._session.begin():
            order = await self._orders.get_by_number(number)
            if order is None:
                raise _not_found(number)
            return to_admin_order_out(order, self._storage)


def _check_shipment_details(pickup: bool, request: ShipRequest) -> None:
    given = (request.carrier is not None, request.tracking_number is not None)
    if pickup and any(given):
        problem = "Дэлгүүрээс авах захиалгад тээвэрлэгч, илгээмжийн дугаар оруулахгүй."
    elif not pickup and not all(given):
        problem = "Тээвэрлэгч ба илгээмжийн дугаарыг хоёуланг нь оруулна уу."
    else:
        return
    raise ProblemError(HTTPStatus.UNPROCESSABLE_ENTITY, "Илгээлтийн мэдээлэл буруу", problem)


def _by(admin: User) -> dict[str, object]:
    return {"actor": admin.identifier}


def _not_found(number: str) -> ProblemError:
    return ProblemError(
        HTTPStatus.NOT_FOUND,
        "Захиалга олдсонгүй",
        f"{number} дугаартай захиалга байхгүй байна.",
        type_=ORDER_NOT_FOUND_TYPE,
    )


# Алдааны мессежид орох үйлдэл, төлвийн монгол нэрс. `_require`-ийн `action` нь англи key хэвээр.
_ACTIONS = {
    "ship": "илгээх",
    "mark as delivered": "хүргэгдсэн гэж тэмдэглэх",
    "cancel": "цуцлах",
    "refund": "төлбөрийг нь буцаах",
}
_STATUSES = {
    "pending": "төлбөр хүлээж буй",
    "paid": "төлөгдсөн",
    "shipped": "илгээсэн",
    "delivered": "хүргэгдсэн",
    "cancelled": "цуцлагдсан",
    "refunded": "төлбөр буцаагдсан",
}


def _conflict(order: Order, action: str) -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        f"Захиалгыг {_ACTIONS.get(action, action)} боломжгүй",
        f'{order.number} дугаартай захиалгын төлөв "{_STATUSES.get(order.status, order.status)}" '
        "тул энэ үйлдлийг хийх боломжгүй.",
        type_=INVALID_TRANSITION_TYPE,
    )


def _request_conflict() -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Хүсэлтийн төлөв өөрчлөгдсөн",
        "Энэ хүсэлтэд тухайн үйлдэл хамаарахаа больсон. Захиалгаа шинэчилж харна уу.",
        type_=INVALID_TRANSITION_TYPE,
    )


def _provider_error(exc: Exception) -> ProblemError:
    log.warning("order_action_provider_error", error=str(exc))
    return ProblemError(
        HTTPStatus.BAD_GATEWAY,
        "Төлбөрийн үйлчилгээ хариу өгсөнгүй",
        "Юу ч өөрчлөгдөөгүй. Хэсэг хүлээгээд дахин оролдоно уу.",
        type_=PAYMENT_PROVIDER_TYPE,
    )
