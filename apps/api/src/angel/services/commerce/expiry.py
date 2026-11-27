"""Дэвсгэрт ажилладаг цэвэрлэгээ: төлөгдөөгүй захиалгын нөөцийг буцааж, орхигдсон зочны сагсыг
устгана. Хэд хэдэн API process зэрэг ажиллуулсан ч аюулгүй: захиалга бүрийг мөрийг нь түгжсэн
үед, pending хэвээр байвал л хаана. Төлбөрийг хоёр удаа цуцлахад хор хөнөөлгүй."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from angel.core.config import Settings
from angel.core.logging import get_logger
from angel.core.mail import Email
from angel.payments import PaymentGateway, PaymentProviderError
from angel.repositories.commerce.carts import CartRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.services.commerce.order_lifecycle import release_order
from angel.services.commerce.order_text import expired_body
from angel.services.commerce.payments import PaymentSettlement
from angel.services.system.outbox import queue_email

log = get_logger(__name__)

BATCH = 50


class OrderExpirer:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway | None,
        settings: Settings,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway
        self._settings = settings

    async def run_once(self) -> int:
        """TTL-ээс хуучин бүх pending захиалгыг хааж, буцаах ёстой төлбөрийг дахин оролдоно. Нөөцийг
        нь чөлөөлсөн захиалгын тоог буцаана."""
        released = await self._expire_overdue()
        await self._retry_refunds()
        async with self._sessions() as session, session.begin():
            guest_cutoff = datetime.now(UTC) - timedelta(days=self._settings.cart_guest_ttl_days)
            await CartRepository(session).delete_stale_guest_carts(guest_cutoff)
        return released

    async def _expire_overdue(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=self._settings.order_pending_ttl_minutes)
        released = 0
        after: tuple[datetime, int] | None = None
        while True:
            async with self._sessions() as session, session.begin():
                batch = await OrderRepository(session).pending_older_than(
                    cutoff, BATCH, after=after
                )
                candidates = [
                    (order.id, order.payment.provider_payment_id if order.payment else None)
                    for order in batch
                ]
                if batch:
                    after = (batch[-1].created_at, batch[-1].id)
            for order_id, intent_id in candidates:
                try:
                    if await self._expire(order_id, intent_id):
                        released += 1
                except Exception:  # нэг захиалгын алдаа бусдыг нь зогсоохгүй
                    log.exception("order_expiry_failed", order_id=order_id)
            if len(candidates) < BATCH:
                return released

    async def _retry_refunds(self) -> None:
        if self._gateway is None:
            return
        after_id = 0
        while True:
            async with self._sessions() as session, session.begin():
                owed = await OrderRepository(session).owing_refunds(
                    BATCH,
                    idle_for=timedelta(minutes=self._settings.refund_retry_minutes),
                    after_id=after_id,
                )
            for order_id in owed:
                try:
                    async with self._sessions() as session:
                        await self._settlement(session, self._gateway).refund_owed(order_id)
                except PaymentProviderError:
                    pass  # settlement log-д бичсэн; дараагийн sweep дахин оролдоно
                except Exception:
                    log.exception("refund_retry_failed", order_id=order_id)
            if len(owed) < BATCH:
                return
            after_id = owed[-1]

    def _settlement(self, session: AsyncSession, gateway: PaymentGateway) -> PaymentSettlement:
        return PaymentSettlement(session, gateway, self._settings)

    async def _expire(self, order_id: int, intent_id: str | None) -> bool:
        if intent_id is not None:
            if self._gateway is None:
                return False
            try:
                outcome = await self._gateway.cancel_intent(intent_id)
            except PaymentProviderError as exc:
                log.warning("order_expiry_deferred", order_id=order_id, error=str(exc))
                return False  # дараагийн sweep дээр дахин оролдоно
            if outcome == "succeeded":
                # Захиалга аль хэдийн төлөгдсөн байна. Мэдэгдэл алдагдсан байж болох тул энд өөрсдөө
                # төлөгдсөн болгоно.
                async with self._sessions() as session:
                    await self._settlement(session, self._gateway).reconcile(intent_id)
                return False
        async with self._sessions() as session, session.begin():
            order = await OrderRepository(session).get_for_update(order_id)
            if order is None:
                return False
            released = await release_order(session, order, "expired")
            if released:
                queue_email(
                    session,
                    Email(
                        to=order.contact_email,
                        subject=f"{order.number} дугаартай захиалгын хугацаа дууслаа",
                        body=expired_body(order),
                    ),
                )
        if released:
            log.info("order_expired", order_id=order_id)
        return released

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("order_expiry_failed")
            await asyncio.sleep(self._settings.order_sweep_interval_seconds)
