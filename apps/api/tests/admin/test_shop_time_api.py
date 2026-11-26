"""Өдрийн хил дэлгүүрийн цагаар (`SHOP_TIMEZONE`), өгөгдөл нь UTC-ээр хадгалагдсан ч.

Тестүүд өдрийн эхэн, төгсгөлийн агшныг тодорхой тавьдаг тул хэдэн цагт ажиллуулахаас үл хамаарна."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from angel.core.config import Settings
from tests.admin.test_admin_orders_api import administrator, in_stock, place_order, warehouse_worker
from tests.conftest import ApiFactory

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

ADMIN = "/api/v1/admin"
ULAANBAATAR = ZoneInfo("Asia/Ulaanbaatar")  # UTC+8


def at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, ULAANBAATAR)


async def set_order_time(engine: AsyncEngine, number: str, column: str, when: datetime) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(f"UPDATE orders SET {column} = :when WHERE number = :n"),  # noqa: S608 - тест
            {"when": when, "n": number},
        )


async def test_a_sale_just_after_local_midnight_belongs_to_the_new_day(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        admin = await administrator(api, db_engine)
        _, number = await place_order(api, in_stock(api, 0), pay=True)
        day = datetime.now(ULAANBAATAR).date() - timedelta(days=3)
        just_after_midnight = at(day, time(0, 30))  # UTC-ээр өмнөх өдрийн 16:30
        await set_order_time(db_engine, number, "paid_at", just_after_midnight)
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE users SET created_at = :when WHERE id = "
                    "(SELECT user_id FROM orders WHERE number = :n)"
                ),
                {"when": just_after_midnight, "n": number},
            )

        async def figures(on: date) -> tuple[int, int, int, int, str]:
            response = await api.client.get(
                f"{ADMIN}/stats", params={"start": f"{on}", "end": f"{on}"}, headers=admin.auth
            )
            assert response.status_code == 200, response.text
            [point] = response.json()["series"]
            return (
                point["revenue_cents"],
                point["orders"],
                point["units"],
                point["new_customers"],
                point["date"],
            )

        revenue, *counts = await figures(day)
        assert revenue > 0
        assert counts == [1, 2, 1, f"{day}"]
        assert await figures(day - timedelta(days=1)) == (0, 0, 0, 0, f"{day - timedelta(days=1)}")


# Аль ч агшинд эдгээрийн нэгнийх нь огноо UTC-ийнхээс өөр байна.
@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
async def test_the_period_may_end_on_the_shops_today_but_not_later(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path, zone: str
) -> None:
    async with api_factory(seed_count=3, media_dir=tmp_path, shop_timezone=zone) as api:
        admin = await administrator(api, db_engine)
        today = datetime.now(ZoneInfo(zone)).date()

        ending_today = await api.client.get(
            f"{ADMIN}/stats", params={"start": f"{today}", "end": f"{today}"}, headers=admin.auth
        )
        default = await api.client.get(f"{ADMIN}/stats", params={"days": 1}, headers=admin.auth)
        tomorrow = today + timedelta(days=1)
        ending_tomorrow = await api.client.get(
            f"{ADMIN}/stats",
            params={"start": f"{today}", "end": f"{tomorrow}"},
            headers=admin.auth,
        )

        assert ending_today.status_code == 200, ending_today.text
        assert default.json()["end"] == f"{today}"
        assert ending_tomorrow.status_code == 422


async def test_the_warehouse_counts_today_from_local_midnight(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        _, early_today = await place_order(api, in_stock(api, 0), pay=True)
        _, late_yesterday = await place_order(api, in_stock(api, 1), pay=True)
        today = datetime.now(ULAANBAATAR).date()
        for column in ("shipped_at", "delivered_at"):
            await set_order_time(db_engine, early_today, column, at(today, time(0, 0, 1)))
            await set_order_time(
                db_engine, late_yesterday, column, at(today - timedelta(days=1), time(23, 59, 59))
            )

        board = (await api.client.get(f"{ADMIN}/fulfillment", headers=worker.auth)).json()

        assert (board["shipped_today"], board["delivered_today"]) == (1, 1)


def test_an_unknown_time_zone_stops_the_server_from_starting() -> None:
    with pytest.raises(ValidationError, match="SHOP_TIMEZONE"):
        Settings(app_env="test", shop_timezone="Asia/Ulanbator-typo")
