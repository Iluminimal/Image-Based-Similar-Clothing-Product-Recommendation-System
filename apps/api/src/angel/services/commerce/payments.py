"""Төлбөр шийдвэрлэх: provider-ийн баталгаажсан төлбөрийг захиалгын төлвийн өөрчлөлт болгодог
цорын ганц газар.

QPay-ийн мэдэгдэл, худалдан авагчийн "Төлбөрөө шалгах", offline горимын simulate endpoint бүгд
үүнийг дуудна, тиймээс development-д ажилладаг код production-д ажилладаг код байна."""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.core.money import format_minor
from angel.models import Order, Payment
from angel.payments import PaymentEvent, PaymentGateway, PaymentProviderError
from angel.repositories.commerce.carts import CartRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.services.commerce.order_lifecycle import release_order
from angel.services.commerce.order_text import confirmation_body
from angel.services.system.outbox import queue_email

log = get_logger(__name__)


class PaymentSettlement:
    def __init__(self, session: AsyncSession, gateway: PaymentGateway, settings: Settings) -> None:
        self._session = session
        self._gateway = gateway
        self._settings = settings
        self._orders = OrderRepository(session)

    async def handle(self, event: PaymentEvent) -> None:
        """Нэг баталгаажсан төлбөрийг яг нэг удаа хэрэглэнэ.

        Event id төлвийн өөрчлөлттэй нэг transaction-д хадгалагдана: crash хоёуланг rollback
        хийж дараагийн шалгалт дахин хэрэглэнэ, амжилтын дараах давталт id-г олно. Мөнгийг буцаах
        ёстой бол эхлээд "буцаах ёстой" (`refund_pending`) гэж хадгалж, дараа нь provider-ийг
        дуудна: дуудлага амжилтгүй болсон ч өр мартагдахгүй. Тэр үед `PaymentProviderError`
        шиднэ; дараагийн мэдэгдэл болон sweep дахин оролдоно."""
        async with self._session.begin():
            first_time = await self._orders.record_event(event.id, event.kind)
            payment = await self._orders.get_payment_by_provider_id(event.intent_id)
            if payment is None:  # бидний биш
                log.info("payment_event_unknown_intent", event_id=event.id)
                return
            order = await self._orders.get_for_update(payment.order_id)
            if order is None:
                return
            if first_time:
                confirmation = await self._on_succeeded(order, payment, event)
                if confirmation is not None:
                    queue_email(self._session, confirmation)
            else:
                log.info("payment_event_duplicate", event_id=event.id)
            order_id, owed = order.id, payment.status == "refund_pending"
        if owed:
            await self.refund_owed(order_id)

    async def reconcile(self, intent_id: str) -> bool:
        """Provider "энэ төлөгдсөн" гэсэн ч мэдэгдэл ирээгүй байж болно: өөрөө асууж, төлөгдсөн
        бол тэр даруй шийднэ. Алдааг шиддэггүй (дуудагчийн урсгал өөрийн хариугаа өгнө, sweep
        дахин оролдоно); захиалгыг шийдсэн бол True."""
        try:
            event = await self._gateway.check(intent_id)
            if event is None:
                log.warning("payment_reconcile_not_confirmed", intent_id=intent_id)
                return False
            await self.handle(event)
        except PaymentProviderError as exc:
            log.warning("payment_reconcile_failed", intent_id=intent_id, error=str(exc))
            return False
        return True

    async def refund_owed(self, order_id: int) -> bool:
        """`refund_pending` төлбөрийг буцаана. Захиалгын мөрийг түгжсэн байхад provider-ийг
        дуудна (зэрэг ирсэн хоёр оролдлого хоёр удаа буцаахгүй); idempotency key давтахыг аюулгүй
        болгоно. Буцаасан бол True, өр байхгүй бол False; амжилтгүй бол `PaymentProviderError`."""
        failure: PaymentProviderError | None = None
        async with self._session.begin():
            order = await self._orders.get_for_update(order_id)
            payment = order.payment if order is not None else None
            if order is None or payment is None or payment.status != "refund_pending":
                return False
            reason = payment.last_error or "order_cancelled"
            try:
                payment.refund_id = await self._gateway.refund(
                    payment.provider_payment_id,
                    idempotency_key=f"refund-{payment.provider_payment_id}",
                )
            except PaymentProviderError as exc:
                log.error("refund_failed_will_retry", order=order.number, error=str(exc))
                payment.updated_at = func.now()  # сүүлд оролдсон цаг: sweep эндээс хүлээнэ
                failure = exc
            else:
                payment.status = "refunded"
                self._orders.add_event(order.id, "refunded", {"reason": reason, "automatic": True})
                log.info("refund_completed", order=order.number, reason=reason)
        # Transaction commit хийгдсэний дараа шиднэ: оролдсон цаг хадгалагдсан байна.
        if failure is not None:
            raise failure
        return True

    async def _on_succeeded(
        self, order: Order, payment: Payment, event: PaymentEvent
    ) -> Email | None:
        if payment.status in ("succeeded", "refunded", "refund_pending"):
            return None
        if order.status == "cancelled":
            # Нөөцийг буцаасны дараа төлөгдсөн (дууссан, эсвэл шинэ checkout-оор солигдсон). Бараа
            # алга болсон байж болох тул оронд нь мөнгийг буцаана.
            _owe_refund(payment, "order_cancelled")
            log.warning("payment_after_cancel", order=order.number)
            return None
        # Захиалгын дүнтэй биш, gateway-ээр авахаар түгжсэн дүнтэй (`charge_minor`) харьцуулна.
        if event.amount != payment.charge_minor or event.currency != payment.charge_currency:
            log.error(
                "payment_amount_mismatch",
                order=order.number,
                paid=event.amount,
                currency=event.currency,
                expected=payment.charge_minor,
            )
            await release_order(self._session, order, "amount_mismatch")
            _owe_refund(payment, "amount_mismatch")
            return None
        order.status = "paid"
        order.paid_at = datetime.now(UTC)
        payment.status = "succeeded"
        payment.provider_data = None
        payment.last_error = None
        self._orders.add_event(order.id, "paid", {"amount_cents": payment.amount_cents})
        carts = CartRepository(self._session)
        cart = await carts.find(user_id=order.user_id)
        if cart is not None:  # худалдаж авсан мөрүүд cart-аас гарна; түүнээс хойш нэмсэн нь үлдэнэ
            await carts.remove_lines(cart.id, {(i.product_id, i.size) for i in order.items})
        await self._session.flush()
        return Email(
            to=order.contact_email,
            subject=f"{order.number} дугаартай захиалга баталгаажлаа",
            body=confirmation_body(
                order, format_minor(payment.charge_minor, payment.charge_currency)
            ),
        )


def _owe_refund(payment: Payment, reason: str) -> None:
    payment.status = "refund_pending"
    payment.provider_data = None
    payment.last_error = reason
