from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from angel.models import (
    Order,
    OrderEvent,
    OrderItem,
    OrderRequest,
    Payment,
    ProcessedPaymentEvent,
)
from angel.models.order import OPEN_REQUEST_STATUSES
from angel.repositories.patterns import contains_pattern, prefix_pattern

_WITH_DETAILS = (
    selectinload(Order.items),
    selectinload(Order.payment),
    selectinload(Order.requests),
)
# Шийдэгдэж дуусаагүй хүсэлттэй эсэх.
_HAS_OPEN_REQUEST = Order.requests.any(OrderRequest.status.in_(OPEN_REQUEST_STATUSES))
# Түүхийг нэмж ачаална: түүхийг харуулдаг хуудсуудад.
_WITH_EVENTS = (*_WITH_DETAILS, selectinload(Order.events))


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order, items: Sequence[OrderItem]) -> Order:
        self._session.add(order)
        await self._session.flush()
        for item in items:
            item.order_id = order.id
            self._session.add(item)
        await self._session.flush()
        return order

    async def get_by_idempotency_key(self, user_id: int, key: str) -> Order | None:
        result = await self._session.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.idempotency_key == key)
            .options(*_WITH_DETAILS)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, user_id: int, number: str) -> Order | None:
        """Эзэмшигчээр хязгаарлана: өөр хүний захиалгын дугаар андуурсан дугаараас ялгагдахгүй."""
        result = await self._session.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.number == number)
            .options(*_WITH_EVENTS)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self._session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(*_WITH_DETAILS)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, order_id: int) -> Order | None:
        """Захиалгын мөрийг түгжинэ; төлөв өөрчлөлтийг нэг нэгээр нь шийднэ. Мөрүүд болон
        төлбөрийг тусад нь (түгжээгүй) ачаална, учир нь FOR UPDATE болон eager join хамт
        ажилладаггүй."""
        result = await self._session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(*_WITH_DETAILS)
            .with_for_update(of=Order)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int, *, limit: int, offset: int) -> list[Order]:
        result = await self._session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .options(*_WITH_DETAILS)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count_for_user(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Order).where(Order.user_id == user_id)
        )
        return int(result.scalar_one())

    # --- admin: бүх хэрэглэгчийн захиалга ---

    @staticmethod
    def _admin_clauses(text_query: str | None, status: str) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = []
        if text_query:
            clauses.append(
                or_(
                    Order.number.ilike(prefix_pattern(text_query), escape="\\"),
                    Order.contact_email.ilike(contains_pattern(text_query), escape="\\"),
                )
            )
        if status == "requests":
            clauses.append(_HAS_OPEN_REQUEST)
        elif status != "all":
            clauses.append(Order.status == status)
        return clauses

    async def list_all(
        self, *, text_query: str | None, status: str, limit: int | None, offset: int
    ) -> tuple[list[Order], int]:
        clauses = self._admin_clauses(text_query, status)
        total = (
            await self._session.execute(select(func.count()).select_from(Order).where(*clauses))
        ).scalar_one()
        rows = await self._session.execute(
            select(Order)
            .where(*clauses)
            .options(*_WITH_DETAILS)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), int(total)

    async def get_by_number(self, number: str) -> Order | None:
        result = await self._session.execute(
            select(Order)
            .where(Order.number == number)
            .options(*_WITH_EVENTS)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def id_for_number(self, number: str) -> int | None:
        result = await self._session.execute(select(Order.id).where(Order.number == number))
        return result.scalar_one_or_none()

    async def status_counts(self, text_query: str | None) -> dict[str, int]:
        """Admin-ы tab бүрийн захиалгын тоо (хайлт үйлчилнэ, төлвийн filter үйлчлэхгүй)."""
        clauses = self._admin_clauses(text_query, "all")
        rows = await self._session.execute(
            select(Order.status, func.count()).where(*clauses).group_by(Order.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def open_request_count(self, text_query: str | None) -> int:
        """Хайлтад таарах, шийдэгдэж дуусаагүй хүсэлттэй захиалгын тоо ("Хүсэлт" tab)."""
        clauses = self._admin_clauses(text_query, "requests")
        result = await self._session.execute(
            select(func.count()).select_from(Order).where(*clauses)
        )
        return int(result.scalar_one())

    def add_event(
        self,
        order_id: int,
        event_type: str,
        data: dict[str, object] | None = None,
        actor_id: int | None = None,
    ) -> None:
        """Дуудагчийн transaction-ийн хэсэг: өөрчлөлт хийгдсэн тохиолдолд л event үүснэ."""
        self._session.add(
            OrderEvent(order_id=order_id, type=event_type, data=data or {}, actor_id=actor_id)
        )

    async def committed_units(self, product_ids: Sequence[int]) -> dict[int, int]:
        """Бараа бүрээс хэдэн ширхэг захиалагдсан ч илгээгдээгүй вэ (төлбөр хүлээж буй эсвэл
        төлсөн). Тэдгээр нь зарах боломжтой тооноос хасагдсан ч агуулахад байгаа хэвээр."""
        if not product_ids:
            return {}
        result = await self._session.execute(
            select(OrderItem.product_id, func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id.in_(product_ids), Order.status.in_(("pending", "paid")))
            .group_by(OrderItem.product_id)
        )
        return {product_id: int(units) for product_id, units in result.all()}

    async def ordered_product_ids(self, product_ids: Sequence[int]) -> set[int]:
        """Аль барааг хэзээ нэгэн цагт захиалсан бэ (цуцалсан захиалга ч тооцогдоно: захиалгын
        мөр бараа руугаа заасаар байдаг)."""
        if not product_ids:
            return set()
        result = await self._session.execute(
            select(OrderItem.product_id).where(OrderItem.product_id.in_(product_ids)).distinct()
        )
        return set(result.scalars())

    async def contact_emails_of(self, user_id: int) -> list[str]:
        result = await self._session.execute(
            select(Order.contact_email).where(Order.user_id == user_id).distinct()
        )
        return list(result.scalars())

    async def count_open_for_user(self, user_id: int) -> int:
        """Дуусаагүй захиалгын тоо: төлбөр хүлээж буй, төлсөн ч хүргэгдээгүй, эсвэл цуцлах,
        буцаах хүсэлт нь шийдэгдээгүй."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Order)
            .where(
                Order.user_id == user_id,
                or_(Order.status.in_(("pending", "paid", "shipped")), _HAS_OPEN_REQUEST),
            )
        )
        return int(result.scalar_one())

    async def pending_for_user(self, user_id: int) -> list[Order]:
        result = await self._session.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.status == "pending")
            .options(selectinload(Order.payment))
            .order_by(Order.id)
        )
        return list(result.scalars())

    async def pending_older_than(
        self, cutoff: datetime, limit: int, *, after: tuple[datetime, int] | None = None
    ) -> list[Order]:
        """Хугацаа хэтэрсэн pending захиалгын нэг багц, хуучин нь эхэнд. `after` (created_at, id)
        өмнөх багцын сүүлчийнхээс үргэлжлүүлнэ: хааж чадаагүй захиалга ардахаа бөглөхгүй."""
        statement = select(Order).where(Order.status == "pending", Order.created_at < cutoff)
        if after is not None:
            statement = statement.where(tuple_(Order.created_at, Order.id) > tuple_(*after))
        result = await self._session.execute(
            statement.options(selectinload(Order.payment))
            .order_by(Order.created_at, Order.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def owing_refunds(
        self, limit: int, *, idle_for: timedelta, after_id: int = 0
    ) -> list[int]:
        """Мөнгийг нь буцаах ёстой хэвээр бөгөөд сүүлд оролдсоноос хойш `idle_for` өнгөрсөн
        захиалгуудын id."""
        result = await self._session.execute(
            select(Payment.order_id)
            .where(
                Payment.status == "refund_pending",
                Payment.updated_at <= func.now() - idle_for,
                Payment.order_id > after_id,
            )
            .order_by(Payment.order_id)
            .limit(limit)
        )
        return list(result.scalars())

    async def add_payment_if_missing(self, payment: Payment) -> None:
        """Давтагдсан checkout нь төлбөр үүсгэж буй өмнөх хүсэлттэй өрсөлдөж болно: unique
        `order_id` нь хоёр дахь insert-ийг юу ч хийхгүй болгоно."""
        await self._session.execute(
            insert(Payment)
            .values(
                order_id=payment.order_id,
                provider=payment.provider,
                provider_payment_id=payment.provider_payment_id,
                provider_data=payment.provider_data,
                status=payment.status,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                charge_currency=payment.charge_currency,
                charge_minor=payment.charge_minor,
                exchange_rate=payment.exchange_rate,
            )
            .on_conflict_do_nothing(index_elements=[Payment.order_id])
        )

    async def get_payment_by_provider_id(self, provider_payment_id: str) -> Payment | None:
        result = await self._session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        return result.scalar_one_or_none()

    async def record_event(self, event_id: str, event_type: str) -> bool:
        """Event id анх харагдахад True, дахин хүргэгдэх бүрд False."""
        result = await self._session.execute(
            insert(ProcessedPaymentEvent)
            .values(id=event_id, type=event_type)
            .on_conflict_do_nothing()
            .returning(ProcessedPaymentEvent.id)
        )
        return result.scalar_one_or_none() is not None
