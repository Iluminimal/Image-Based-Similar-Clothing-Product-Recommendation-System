"""Цуцлах, буцаах хүсэлтийг унших, бичих. Өөрчлөхөөсөө өмнө дуудсан код захиалгын мөрийг түгжсэн
байх ёстой."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from angel.models import Order, OrderRequest
from angel.models.order import OPEN_REQUEST_STATUSES


class OrderRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, request: OrderRequest) -> None:
        self._session.add(request)

    async def forget_written_by(self, user_id: int) -> None:
        """Account устгахад хэрэглэнэ: хэрэглэгчийн өөрийн бичсэн тайлбарыг арилгана (шалтгааны
        ангилал үлдэнэ)."""
        own = select(Order.id).where(Order.user_id == user_id)
        await self._session.execute(
            update(OrderRequest).where(OrderRequest.order_id.in_(own)).values(details=None)
        )

    async def open_counts(self) -> dict[tuple[str, str], int]:
        """Нээлттэй хүсэлтийн тоо, (төрөл, төлөв) тус бүрээр."""
        rows = await self._session.execute(
            select(OrderRequest.kind, OrderRequest.status, func.count())
            .where(OrderRequest.status.in_(OPEN_REQUEST_STATUSES))
            .group_by(OrderRequest.kind, OrderRequest.status)
        )
        return {(kind, status): int(count) for kind, status, count in rows.all()}

    async def expected_returns(self, limit: int) -> tuple[list[tuple[OrderRequest, Order]], int]:
        """Зөвшөөрөгдсөн ч бараа нь хараахан ирээгүй буцаалтууд (хамгийн эрт зөвшөөрсөн нь эхэнд)
        болон тэдгээрийн тоо."""
        waiting = (OrderRequest.kind == "return", OrderRequest.status == "approved")
        total = (
            await self._session.execute(
                select(func.count()).select_from(OrderRequest).where(*waiting)
            )
        ).scalar_one()
        rows = await self._session.execute(
            select(OrderRequest, Order)
            .join(Order, Order.id == OrderRequest.order_id)
            .where(*waiting)
            .options(selectinload(Order.items))
            .order_by(OrderRequest.decided_at, OrderRequest.id)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in rows.all()], int(total)
