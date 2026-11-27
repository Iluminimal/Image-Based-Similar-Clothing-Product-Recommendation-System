"""Checkout: сагсыг нөөц эзлэх pending захиалга болгоод төлбөрийг эхлүүлнэ.

Захиалгыг гурван богино transaction-оор үүсгэнэ. Төлбөрийн provider руу хийх дуудлагыг тэдгээрийн
хооронд хийнэ, transaction дотор хэзээ ч хийхгүй: сүлжээ хүлээж буй transaction хариу иртэл мөрийн
түгжээг барьсаар байдаг.

1. idempotency key-г хайж, хэрэглэгчийн өмнөх төлөгдөөгүй захиалгуудыг олно;
2. тэдгээрийн төлбөрийг provider дээр цуцална (transaction-гүй);
3. нэг transaction: нөөцийн мөрүүдийг id-ийн дарааллаар түгжиж, сагсыг дахин шалгаж, нөөцийг хасаж,
   захиалгыг үнийн snapshot-той нь бичнэ;
4. төлбөр үүсгэж (transaction-гүй), дараа нь хадгална.

Хүсэлтийг ижил `Idempotency-Key`-тэй давтвал дутуу үлдсэн алхмаас үргэлжилнэ. Тиймээс хаана ч
timeout болсон client хүсэлтээ дахин илгээхэд л болно."""

import contextlib
import hashlib
import secrets
from collections import defaultdict
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.errors import (
    ADDRESS_NOT_FOUND_TYPE,
    ATTEMPT_EXPIRED_TYPE,
    CART_EMPTY_TYPE,
    CHECKOUT_BUSY_TYPE,
    CONTACT_EMAIL_REQUIRED_TYPE,
    IDEMPOTENCY_KEY_REUSED_TYPE,
    INSUFFICIENT_STOCK_TYPE,
    ORDER_NOT_FOUND_TYPE,
    PAYMENT_IN_PROGRESS_TYPE,
    PAYMENT_PROVIDER_TYPE,
    PAYMENTS_UNAVAILABLE_TYPE,
    PRICE_CHANGED_TYPE,
    SHIPPING_UNAVAILABLE_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.models import Order, OrderItem, Payment
from angel.payments import IntentInfo, PaymentEvent, PaymentGateway, PaymentProviderError
from angel.repositories.accounts.users import AddressRepository, UserRepository
from angel.repositories.catalog.products import ProductRepository
from angel.repositories.commerce.carts import CartRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.schemas.accounts.address import AddressSnapshot
from angel.schemas.commerce.order import (
    CheckoutOut,
    CheckoutRequest,
    OrderOut,
    PaymentMethodOut,
    PaymentOut,
    QPayCheckoutOut,
    ShippingMethodList,
    ShippingZone,
)
from angel.services.commerce.cart import validate_size
from angel.services.commerce.order_lifecycle import release_order
from angel.services.commerce.payments import PaymentSettlement
from angel.services.commerce.shipping import (
    available_methods,
    shipping_cost,
    shipping_methods,
    zone_for,
)
from angel.services.mappers import to_charge_out, to_order_out
from angel.storage import Storage

log = get_logger(__name__)

# 0/O/1/I байхгүй: захиалгын дугаарыг утсаар уншиж өгдөг.
MAX_ATTEMPTS = 5
_NUMBER_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def new_order_number() -> str:
    return "LK-" + "".join(secrets.choice(_NUMBER_ALPHABET) for _ in range(8))


def request_hash(request: CheckoutRequest) -> str:
    """Захиалгыг тодорхойлдог талбарууд. `expected_total_cents` орохгүй: энэ шинэ захиалгыг
    тодорхойлдоггүй, зөвхөн хэрэглэгчийн зөвшөөрсөн дүнг шалгахад хэрэгтэй."""
    fields = request.model_dump_json(include={"address_id", "shipping_method", "contact_email"})
    return hashlib.sha256(fields.encode()).hexdigest()


def _require_same_request(order: Order, request: CheckoutRequest) -> None:
    if order.request_hash is not None and order.request_hash != request_hash(request):
        raise ProblemError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Захиалгын мэдээлэл өөрчлөгдсөн байна",
            "Хуудсаа шинэчлээд захиалгаа дахин илгээнэ үү.",
            type_=IDEMPOTENCY_KEY_REUSED_TYPE,
        )


def _require_expected_total(request: CheckoutRequest, total: int) -> None:
    if request.expected_total_cents is not None and request.expected_total_cents != total:
        raise ProblemError(
            HTTPStatus.CONFLICT,
            "Үнэ өөрчлөгдсөн байна",
            "Захиалгын нийт дүн өөрчлөгдлөө. Шинэ дүнг шалгаад дахин баталгаажуулна уу.",
            type_=PRICE_CHANGED_TYPE,
            extensions={"total_cents": total},
        )


class CheckoutService:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        settings: Settings,
        gateway: PaymentGateway | None,
        settlement: PaymentSettlement | None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._gateway = gateway
        self._settlement = settlement
        self._orders = OrderRepository(session)
        self._products = ProductRepository(session)
        self._carts = CartRepository(session)
        self._addresses = AddressRepository(session)

    def shipping_methods(self, zone: ShippingZone = "ub") -> ShippingMethodList:
        return shipping_methods(self._settings, zone)

    def payment_method(self) -> PaymentMethodOut:
        gateway = self._gateway
        return PaymentMethodOut(
            provider=gateway.mode if gateway else None,
            charge_currency=(gateway.charge_currency if gateway else None)
            or self._settings.currency,
        )

    async def create_checkout(
        self, user_id: int, request: CheckoutRequest, idempotency_key: str
    ) -> CheckoutOut:
        gateway = self._require_gateway()

        order_id = await self._existing_order_id(user_id, request, idempotency_key)
        if order_id is None:
            # Хэрэглэгчийн өмнөх төлөгдөөгүй захиалгуудын нөөцийг шинэ захиалгад өгөхөөс өмнө
            # provider дээр тэдний төлбөрийг цуцлах ёстой, эс бөгөөс хоёулаа төлөгдөж болно. Энэ нь
            # сүлжээний дуудлага тул transaction-уудын хооронд хийнэ. Энэ хооронд тэр хэрэглэгчийн
            # өөр checkout шинэ төлөгдөөгүй захиалга нэмсэн бол дахин нэг тойрно.
            cancelled: set[int] = set()
            for _ in range(MAX_ATTEMPTS):
                placed = await self._place_order(user_id, request, idempotency_key, cancelled)
                if isinstance(placed, int):
                    order_id = placed
                    break
                for old_id, intent_id in placed.items():
                    if await self._cancel_payment(gateway, intent_id) == "succeeded":
                        # Хуучин захиалга аль хэдийн төлөгдсөн байна: түүнийг шийдэж, шинэ захиалга
                        # үүсгэхгүй.
                        if self._settlement is not None:
                            await self._settlement.reconcile(intent_id)
                        raise ProblemError(
                            HTTPStatus.CONFLICT,
                            "Төлбөр хийгдэж байна",
                            "Таны өмнөх захиалга дөнгөж төлөгдлөө. Өөр захиалга хийхээсээ өмнө "
                            "захиалгуудаа шалгана уу.",
                            type_=PAYMENT_IN_PROGRESS_TYPE,
                        )
                    cancelled.add(old_id)
            else:
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Захиалга боловсруулагдаж байна",
                    "Хэд хэдэн захиалга зэрэг хийгдлээ. Дахин оролдоно уу.",
                    type_=CHECKOUT_BUSY_TYPE,
                )

        return await self._complete(user_id, order_id, gateway)

    async def simulate_payment(self, user_id: int, number: str) -> OrderOut:
        """Зөвхөн offline горим: provider баталгаажуулсан мэт захиалгыг төлнө."""
        gateway = self._require_gateway()
        if gateway.mode != "offline" or self._settlement is None:
            raise ProblemError(HTTPStatus.NOT_FOUND, "Олдсонгүй")
        async with self._session.begin():
            order = await self._orders.get_for_user(user_id, number)
            if order is None:
                raise self._order_not_found()
            if order.status == "cancelled" or order.payment is None:
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Энэ захиалгыг төлөх боломжгүй болсон",
                    type_=PAYMENT_IN_PROGRESS_TYPE,
                )
            event = PaymentEvent(
                id=f"evt_offline_{uuid4().hex}",
                intent_id=order.payment.provider_payment_id,
                amount=order.payment.charge_minor,
                currency=order.payment.charge_currency,
            )
            already_paid = order.status == "paid"
        if not already_paid:
            await self._settlement.handle(event)
        async with self._session.begin():
            fresh = await self._orders.get_for_user(user_id, number)
            assert fresh is not None
            return to_order_out(
                fresh, self._storage, pending_ttl_minutes=self._settings.order_pending_ttl_minutes
            )

    async def check_payment(self, user_id: int, number: str) -> OrderOut:
        """Худалдан авагч "Төлбөрөө шалгах" дарсан эсвэл хуудас руу буцаж ирсэн үед provider-оос
        төлвийг асууна. Төлөгдсөн бол захиалгыг төлөгдсөн болгоно. Олон удаа дуудахад аюулгүй."""
        gateway = self._require_gateway()
        async with self._session.begin():
            order = await self._orders.get_for_user(user_id, number)
            if order is None:
                raise self._order_not_found()
            intent_id = order.payment.provider_payment_id if order.payment else None
            open_payment = order.status in ("pending", "cancelled") and intent_id is not None
        if open_payment and intent_id is not None and self._settlement is not None:
            try:
                event = await gateway.check(intent_id)
            except PaymentProviderError as exc:
                raise ProblemError(
                    HTTPStatus.BAD_GATEWAY,
                    "Төлбөрийн үйлчилгээ боломжгүй",
                    "Төлбөрийг одоо шалгаж чадсангүй. Дахин оролдоно уу.",
                    type_=PAYMENT_PROVIDER_TYPE,
                ) from exc
            if event is not None:
                # Төлбөр буцаалт амжилтгүй болсон ч буцаах мөнгө бүртгэлтэй үлдэнэ: sweep дахин
                # оролдоно.
                with contextlib.suppress(PaymentProviderError):
                    await self._settlement.handle(event)
        async with self._session.begin():
            fresh = await self._orders.get_for_user(user_id, number)
            assert fresh is not None
            return to_order_out(
                fresh, self._storage, pending_ttl_minutes=self._settings.order_pending_ttl_minutes
            )

    # --- алхмууд ---

    async def _existing_order_id(
        self, user_id: int, request: CheckoutRequest, idempotency_key: str
    ) -> int | None:
        async with self._session.begin():
            await self._lock_user(user_id)
            existing = await self._orders.get_by_idempotency_key(user_id, idempotency_key)
            if existing is None:
                return None
            _require_same_request(existing, request)
            return existing.id

    async def _place_order(
        self,
        user_id: int,
        request: CheckoutRequest,
        idempotency_key: str,
        cancelled: set[int],
    ) -> int | dict[int, str]:
        """Захиалгын id-г буцаана. Эсвэл эхлээд provider дээр төлбөрийг нь цуцлах ёстой төлөгдөөгүй
        захиалгуудыг {order id: payment id} хэлбэрээр буцаана (энэ үед юу ч өөрчлөхгүй)."""
        async with self._session.begin():
            await self._lock_user(user_id)
            # Ижил key-тэй зэрэг ирсэн хүсэлт бид сүүлд шалгаснаас хойш дуусчихжээ.
            existing = await self._orders.get_by_idempotency_key(user_id, idempotency_key)
            if existing is not None:
                _require_same_request(existing, request)
                return existing.id

            pending = await self._orders.pending_for_user(user_id)
            uncancelled = {
                order.id: order.payment.provider_payment_id
                for order in pending
                if order.payment is not None and order.id not in cancelled
            }
            if uncancelled:
                # Хуучин нэхэмжлэхийг цуцлахаас ӨМНӨ дүнг шалгана: татгалзах гэж буй хүсэлт худалдан
                # авагчийн төлж болох QR-ыг хүчингүй болгох ёсгүй.
                await self._check_total_early(user_id, request)
                return uncancelled

            stale: list[Order] = []
            for old in pending:
                locked = await self._orders.get_for_update(old.id)
                if locked is None or locked.status != "pending":
                    continue
                stale.append(locked)

            user = await UserRepository(self._session).get(user_id)
            address = await self._addresses.get(user_id, request.address_id)
            if address is None:
                raise ProblemError(
                    HTTPStatus.NOT_FOUND,
                    "Хаяг олдсонгүй",
                    "Хадгалсан хаягуудын аль нэгийг сонгоно уу.",
                    type_=ADDRESS_NOT_FOUND_TYPE,
                )
            zone = zone_for(address.region)
            if request.shipping_method not in available_methods(zone):
                raise ProblemError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "Энэ хүргэлтийг сонгох боломжгүй",
                    "Шуурхай хүргэлт зөвхөн Улаанбаатарт байна. Хүргэлтийн өөр төрөл сонгоно уу.",
                    type_=SHIPPING_UNAVAILABLE_TYPE,
                )
            assert user is not None  # token-ийн subject; хэрэглэгч хэзээ ч устгагддаггүй
            contact_email = request.contact_email or user.email
            if contact_email is None:
                raise ProblemError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "Захиалгад имэйл шаардлагатай",
                    "Захиалгын мэдээлэл хүлээн авах имэйл хаягаа оруулна уу.",
                    type_=CONTACT_EMAIL_REQUIRED_TYPE,
                )
            cart = await self._carts.find(user_id=user_id)
            if cart is None or not cart.items:
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Сагс хоосон байна",
                    type_=CART_EMPTY_TYPE,
                )

            # Энэ transaction-д хамаарах бүх барааг нэг эрэмбэлсэн statement-ээр түгжинэ.
            product_ids = {item.product_id for item in cart.items}
            product_ids |= {item.product_id for order in stale for item in order.items}
            products = await self._products.get_many(sorted(product_ids), for_update=True)
            for order in stale:
                await release_order(self._session, order, "replaced")

            needed: dict[int, int] = defaultdict(int)
            problems: list[dict[str, Any]] = []
            for line in cart.items:
                product = products.get(line.product_id)
                if product is None or not product.is_active:
                    problems.append(
                        {"product_id": line.product_id, "size": line.size, "available": 0}
                    )
                    continue
                try:
                    validate_size(product, line.size)
                except ProblemError:
                    problems.append(
                        {"product_id": line.product_id, "size": line.size, "available": 0}
                    )
                    continue
                needed[line.product_id] += line.quantity
            for product_id, quantity in needed.items():
                available = products[product_id].stock_quantity
                if quantity > available:
                    problems.append({"product_id": product_id, "available": available})
            if problems:
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Зарим бараа дууссан байна",
                    "Сагсаа шинэчлээд дахин оролдоно уу.",
                    type_=INSUFFICIENT_STOCK_TYPE,
                    extensions={"issues": problems},
                )

            for product_id, quantity in needed.items():
                products[product_id].stock_quantity -= quantity
            items = [
                OrderItem(
                    product_id=line.product_id,
                    product_name=products[line.product_id].name,
                    product_slug=products[line.product_id].slug,
                    image_key=products[line.product_id].image_key,
                    size=line.size,
                    unit_price_cents=products[line.product_id].price_cents,
                    quantity=line.quantity,
                )
                for line in cart.items
            ]
            subtotal = sum(item.unit_price_cents * item.quantity for item in items)
            shipping = shipping_cost(self._settings, request.shipping_method, subtotal, zone)
            # Эцсийн шалгалт, барааны мөр түгжээтэй байхад: таарахгүй бол бүх зүйл буцна.
            _require_expected_total(request, subtotal + shipping)
            order = Order(
                number=new_order_number(),
                user_id=user_id,
                status="pending",
                idempotency_key=idempotency_key,
                request_hash=request_hash(request),
                currency=self._settings.currency,
                subtotal_cents=subtotal,
                shipping_cents=shipping,
                total_cents=subtotal + shipping,
                shipping_method=request.shipping_method,
                shipping_address=AddressSnapshot.model_validate(
                    address, from_attributes=True
                ).model_dump(),
                contact_email=contact_email,
            )
            await self._orders.add(order, items)
            self._orders.add_event(order.id, "placed")
            return order.id

    async def _check_total_early(self, user_id: int, request: CheckoutRequest) -> None:
        """Түгжээгүй урьдчилсан тооцоо. Бусад бүх шалгалтыг (хаяг, нөөц) дараагийн алхам хийнэ:
        энд тооцож чадахгүй бол чимээгүй өнгөрнө."""
        if request.expected_total_cents is None:
            return
        address = await self._addresses.get(user_id, request.address_id)
        cart = await self._carts.find(user_id=user_id)
        if address is None or cart is None or not cart.items:
            return
        zone = zone_for(address.region)
        if request.shipping_method not in available_methods(zone):
            return
        products = await self._products.get_many([item.product_id for item in cart.items])
        if any(item.product_id not in products for item in cart.items):
            return
        subtotal = sum(products[i.product_id].price_cents * i.quantity for i in cart.items)
        shipping = shipping_cost(self._settings, request.shipping_method, subtotal, zone)
        _require_expected_total(request, subtotal + shipping)

    async def _complete(self, user_id: int, order_id: int, gateway: PaymentGateway) -> CheckoutOut:
        """Захиалгад төлбөр байгаа эсэхийг баталгаажуулаад browser-т тайлбарлана."""
        async with self._session.begin():
            order = await self._orders.get_by_id(order_id)
            assert order is not None
            if order.status == "cancelled":
                # Ижил key-тэй давтсан хүсэлт, гэхдээ тэр захиалгын хугацаа дууссан (эсвэл
                # цуцлагдсан): шинэ оролдлого хийх ёстой.
                raise ProblemError(
                    HTTPStatus.CONFLICT,
                    "Захиалгын хугацаа дууссан",
                    "Энэ захиалга цуцлагдсан байна. Дахин захиална уу.",
                    type_=ATTEMPT_EXPIRED_TYPE,
                )
            number, total, currency = order.number, order.total_cents, order.currency
            needs_payment = order.status == "pending" and order.payment is None

        if needs_payment:
            await self._create_payment(order_id, number, total, currency, gateway)

        async with self._session.begin():
            final = await self._orders.get_for_user(user_id, number)
            assert final is not None
            payment = final.payment
            data = payment.provider_data if payment and final.status == "pending" else None
            return CheckoutOut(
                order=to_order_out(
                    final,
                    self._storage,
                    pending_ttl_minutes=self._settings.order_pending_ttl_minutes,
                ),
                payment=PaymentOut(
                    provider=gateway.mode,
                    charge=to_charge_out(payment),
                    qpay=QPayCheckoutOut.model_validate(data) if data else None,
                ),
            )

    async def _create_payment(
        self, order_id: int, number: str, total: int, currency: str, gateway: PaymentGateway
    ) -> None:
        """Захиалгын төлбөрийг provider дээр үүсгээд хадгална. Захиалга бүрд яг нэг удаа.

        QPay ижил дугаартай хоёр дахь нэхэмжлэхийг зөвшөөрдөггүй. Тиймээс давхар товшилтоос зэрэг
        ирсэн хүсэлтүүд энд захиалгын advisory lock дээр дараалж хүлээнэ: хоёр дахь нь хадгалсан
        төлбөрийг олж, шинийг үүсгэхгүй. Энэ түгжээ зөвхөн энэ захиалгынх. Сүлжээ хүлээх хооронд
        захиалгын мөрийг түгжихгүй (expiry, админы ажил саатахгүй)."""
        intent: IntentInfo | None = None
        failure: PaymentProviderError | None = None
        still_open = False
        async with self._session.begin():
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"payment:{order_id}"},
            )
            order = await self._orders.get_by_id(order_id)
            if order is None or order.status != "pending" or order.payment is not None:
                return  # өөр хүсэлт аль хэдийн үүсгэсэн, эсвэл захиалга хаагдсан
            # Дэлгүүр төгрөгөөр үнэ тогтоодог тул хөрвүүлэхгүй: худалдан авагчид харуулсан дүнг яг
            # тэр хэвээр нь provider руу илгээнэ. Provider өөр валют шаардвал тохиргоо буруу.
            charge_currency = gateway.charge_currency or currency
            charge_minor = total
            if charge_currency != currency:
                failure = PaymentProviderError(
                    f"{gateway.mode} charges in {charge_currency}, the shop prices in {currency}"
                )
            else:
                try:
                    intent = await gateway.create_intent(
                        amount=charge_minor,
                        currency=charge_currency,
                        order_number=number,
                        idempotency_key=f"order-{order_id}",
                    )
                except PaymentProviderError as exc:
                    failure = exc
                else:
                    current = await self._orders.get_for_update(order_id)
                    still_open = current is not None and current.status == "pending"
                    await self._orders.add_payment_if_missing(
                        Payment(
                            order_id=order_id,
                            provider=gateway.mode,
                            provider_payment_id=intent.id,
                            provider_data=(
                                intent.checkout if still_open and intent.checkout else None
                            ),
                            status="requires_payment" if still_open else "canceled",
                            amount_cents=total,
                            currency=currency,
                            charge_currency=charge_currency,
                            charge_minor=charge_minor,
                            exchange_rate=Decimal(1),
                        )
                    )
        if failure is not None:
            log.error("payment_setup_failed", order=number, error=str(failure))
            await self._abort(order_id)
            raise ProblemError(
                HTTPStatus.BAD_GATEWAY,
                "Төлбөрийн үйлчилгээ боломжгүй",
                "Төлбөрийг эхлүүлж чадсангүй. Таны сагс хэвээр байна, дахин оролдоно уу.",
                type_=PAYMENT_PROVIDER_TYPE,
            ) from failure
        if intent is not None and not still_open:
            # Төлбөр үүсэж байх хооронд захиалга хаагдсан (хугацаа дууссан, солигдсон): нэхэмжлэхийг
            # цуцална.
            with contextlib.suppress(PaymentProviderError):
                await gateway.cancel_intent(intent.id)

    async def _abort(self, order_id: int) -> None:
        """Provider төлбөр үүсгэхээс татгалзсан тул нөөцийг буцаана."""
        async with self._session.begin():
            order = await self._orders.get_for_update(order_id)
            if order is not None and order.payment is None:
                await release_order(self._session, order, "payment_setup_failed")

    async def _cancel_payment(self, gateway: PaymentGateway, intent_id: str) -> str:
        try:
            return await gateway.cancel_intent(intent_id)
        except PaymentProviderError as exc:
            raise ProblemError(
                HTTPStatus.BAD_GATEWAY,
                "Төлбөрийн үйлчилгээ боломжгүй",
                "Өмнөх төлөгдөөгүй захиалгыг солиж чадсангүй. Дахин оролдоно уу.",
                type_=PAYMENT_PROVIDER_TYPE,
            ) from exc

    async def _lock_user(self, user_id: int) -> None:
        """Нэг хэрэглэгчийн checkout-ууд дараалж ажиллана (түгжээ commit хийхэд чөлөөлөгдөнө). Өөр
        хэрэглэгчид бие биеэ энд хүлээхгүй."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"checkout:{user_id}"},
        )

    def _require_gateway(self) -> PaymentGateway:
        if self._gateway is None:
            raise ProblemError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Төлбөр боломжгүй байна",
                "Энэ серверт төлбөр тохируулагдаагүй байна.",
                type_=PAYMENTS_UNAVAILABLE_TYPE,
            )
        return self._gateway

    @staticmethod
    def _order_not_found() -> ProblemError:
        return ProblemError(HTTPStatus.NOT_FOUND, "Захиалга олдсонгүй", type_=ORDER_NOT_FOUND_TYPE)
