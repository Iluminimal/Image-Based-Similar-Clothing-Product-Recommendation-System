from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.config import Settings
from angel.core.shop_time import start_of_day, today
from angel.models import Order, OrderRequest, User
from angel.repositories.admin.fulfillment import FulfillmentRepository
from angel.repositories.commerce.order_requests import OrderRequestRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.schemas.admin.dashboard import LowStockProduct
from angel.schemas.admin.fulfillment import (
    ExpectedReturn,
    FulfillmentBoard,
    QueuedOrder,
    QueueLine,
)
from angel.services.admin.audit import to_audit_entry
from angel.services.mappers import product_image
from angel.storage import Storage

QUEUE_SHOWN = 15
ALERTS_SHOWN = 12
ACTIVITY_SHOWN = 10
AVERAGE_WINDOW_DAYS = 7
LINES_SHOWN = 3
RETURNS_SHOWN = 10


class FulfillmentBoardService:
    def __init__(self, session: AsyncSession, storage: Storage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._board = FulfillmentRepository(session)

    async def board(self, worker: User) -> FulfillmentBoard:
        now = datetime.now(UTC)
        sla = self._settings.ship_sla_hours
        threshold = self._settings.low_stock_threshold
        zone = self._settings.shop_zone
        midnight = start_of_day(today(zone), zone)
        async with self._session.begin():
            to_ship, overdue, oldest = await self._board.paid_summary(now - timedelta(hours=sla))
            queue = await self._board.queue(QUEUE_SHOWN)
            shipped = await self._board.count_since("shipped_at", midnight)
            delivered = await self._board.count_since("delivered_at", midnight)
            average = await self._board.average_ship_hours(
                now - timedelta(days=AVERAGE_WINDOW_DAYS)
            )
            alerts, out_total, low_total = await self._board.stock_alerts(threshold, ALERTS_SHOWN)
            activity = await self._board.activity_of(worker.id, ACTIVITY_SHOWN)
            queued = [self._queued(order, now, sla) for order in queue]
            returns, returns_total = await OrderRequestRepository(self._session).expected_returns(
                RETURNS_SHOWN
            )
            expected = [self._expected(request, order) for request, order in returns]
            held = await OrderRepository(self._session).committed_units([p.id for p in alerts])
            stock_alerts = [
                LowStockProduct(
                    id=p.id,
                    name=p.name,
                    slug=p.slug,
                    stock_quantity=p.stock_quantity,
                    committed=held.get(p.id, 0),
                    on_hand=p.stock_quantity + held.get(p.id, 0),
                    image=product_image(p.image_key, p.blur_data_url, self._storage),
                )
                for p in alerts
            ]
            my_activity = [to_audit_entry(row) for row in activity]
        return FulfillmentBoard(
            sla_hours=sla,
            to_ship=to_ship,
            overdue=overdue,
            oldest_paid_at=oldest,
            shipped_today=shipped,
            delivered_today=delivered,
            avg_ship_hours=average,
            out_of_stock=out_total,
            low_stock=low_total,
            low_stock_threshold=threshold,
            queue=queued,
            returns_expected=expected,
            returns_expected_total=returns_total,
            stock_alerts=stock_alerts,
            my_activity=my_activity,
        )

    def _queued(self, order: Order, now: datetime, sla: int) -> QueuedOrder:
        paid_at = order.paid_at or order.created_at
        waiting = max(0, int((now - paid_at).total_seconds() // 3600))
        return QueuedOrder(
            number=order.number,
            customer_name=order.shipping_address.get("full_name", ""),
            item_count=sum(item.quantity for item in order.items),
            shipping_method=order.shipping_method,
            paid_at=paid_at,
            waiting_hours=waiting,
            overdue=waiting >= sla,
            cancel_requested=any(r.is_open for r in order.requests),
            lines=self._lines(order),
        )

    def _expected(self, request: OrderRequest, order: Order) -> ExpectedReturn:
        return ExpectedReturn(
            number=order.number,
            customer_name=order.shipping_address.get("full_name", ""),
            item_count=sum(item.quantity for item in order.items),
            approved_at=request.decided_at or request.created_at,
            lines=self._lines(order),
        )

    def _lines(self, order: Order) -> list[QueueLine]:
        return [
            QueueLine(
                name=item.product_name,
                quantity=item.quantity,
                image=product_image(item.image_key, None, self._storage),
            )
            for item in order.items[:LINES_SHOWN]
        ]
