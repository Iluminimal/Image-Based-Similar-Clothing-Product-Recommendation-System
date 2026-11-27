"""CSV тайлан татах: зөвхөн админ. Мөнгөн дүнг дэлгүүрт харагддаг нэгжээр, цагийг дэлгүүрийн цагаар
бичнэ."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from angel.core.csv_export import csv_response, local_time_cell, money_cell
from angel.core.deps import AdminDashboardServiceDep, AdminOrderServiceDep, SettingsDep
from angel.schemas.admin.dashboard import StatsQuery
from angel.schemas.admin.orders import AdminOrderListQuery

router = APIRouter(prefix="/export", tags=["export"])


@router.get(
    "/stats",
    summary="Daily revenue, orders, units and new customers of a period as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_stats(
    query: Annotated[StatsQuery, Query()], service: AdminDashboardServiceDep
) -> Response:
    stats = await service.stats(query)
    return csv_response(
        f"angel-stats-{stats.start}-{stats.end}.csv",
        ["date", "revenue", "currency", "orders", "units", "new_customers"],
        [
            [
                p.date,
                money_cell(p.revenue_cents),
                stats.currency,
                p.orders,
                p.units,
                p.new_customers,
            ]
            for p in stats.series
        ],
    )


@router.get(
    "/orders",
    summary="Every order matching the current filter as CSV, newest first",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_orders(
    query: Annotated[AdminOrderListQuery, Query()],
    service: AdminOrderServiceDep,
    settings: SettingsDep,
) -> Response:
    orders = await service.all_matching(query)
    return csv_response(
        "angel-orders.csv",
        [
            "number",
            "created_at_local",
            "status",
            "customer_name",
            "customer_email",
            "items",
            "total",
            "currency",
            "payment_status",
        ],
        [
            [
                o.number,
                local_time_cell(o.created_at, settings.shop_zone),
                o.status,
                o.customer_name,
                o.customer_email,
                o.item_count,
                money_cell(o.total_cents),
                o.currency,
                o.payment_status or "",
            ]
            for o in orders
        ],
    )
