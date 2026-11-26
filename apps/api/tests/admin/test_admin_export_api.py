"""CSV гаргалт: зөвхөн админ, Excel-д нээгдэх, томьёоны инжекцгүй."""

import csv
import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from angel.core.csv_export import money_cell, safe_cell
from tests.admin.test_admin_orders_api import administrator, in_stock, place_order
from tests.conftest import ApiFactory

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

ADMIN = "/api/v1/admin"


def rows(body: str) -> list[list[str]]:
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body.removeprefix("﻿"))))


async def test_the_stats_export_has_one_row_per_day_of_the_period(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        admin = await administrator(api, db_engine)
        await place_order(api, in_stock(api, 0), pay=True)

        response = await api.client.get(
            f"{ADMIN}/export/stats", params={"days": 7}, headers=admin.auth
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert 'attachment; filename="angel-stats-' in response.headers["content-disposition"]
        table = rows(response.text)
        assert table[0] == ["date", "revenue", "currency", "orders", "units", "new_customers"]
        assert len(table) == 1 + 7
        today = (
            await api.client.get(f"{ADMIN}/stats", params={"days": 1}, headers=admin.auth)
        ).json()
        cents = today["revenue_cents"]["current"]
        # Төгрөгөөр: дэлгүүрт харагддаг дүн, 100 дахин их биш.
        assert table[-1][1:5] == [str(cents // 100), "MNT", "1", "2"]


async def test_the_orders_export_follows_the_status_filter(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        admin = await administrator(api, db_engine)
        _, paid = await place_order(api, in_stock(api, 0), pay=True)
        await place_order(api, in_stock(api, 1), pay=False)

        everything = rows((await api.client.get(f"{ADMIN}/export/orders", headers=admin.auth)).text)
        only_paid = rows(
            (
                await api.client.get(
                    f"{ADMIN}/export/orders", params={"status": "paid"}, headers=admin.auth
                )
            ).text
        )

        assert everything[0][0] == "number"
        assert len(everything) == 3
        assert [r[0] for r in only_paid[1:]] == [paid]
        assert only_paid[1][2] == "paid"


async def test_amounts_and_times_read_as_the_shop_shows_them(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        admin = await administrator(api, db_engine)
        _, number = await place_order(api, in_stock(api, 0), pay=True)
        order = (await api.client.get(f"{ADMIN}/orders/{number}", headers=admin.auth)).json()

        header, row = rows(
            (await api.client.get(f"{ADMIN}/export/orders", headers=admin.auth)).text
        )

        exported = dict(zip(header, row, strict=True))
        local = datetime.fromisoformat(order["created_at"]).astimezone(ZoneInfo("Asia/Ulaanbaatar"))
        assert exported["created_at_local"] == local.strftime("%Y-%m-%d %H:%M:%S")
        assert exported["total"] == str(order["total_cents"] // 100)
        assert exported["currency"] == "MNT"


async def test_the_orders_export_is_not_cut_short(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        admin = await administrator(api, db_engine)
        _, number = await place_order(api, in_stock(api, 0), pay=False)
        await copy_order(db_engine, number, times=10_001)

        table = rows((await api.client.get(f"{ADMIN}/export/orders", headers=admin.auth)).text)

        assert len(table) == 1 + 10_002
        assert len({row[0] for row in table[1:]}) == 10_002


async def copy_order(engine: AsyncEngine, number: str, *, times: int) -> None:
    """Захиалгын мөрийг олшруулна (зөвхөн жагсаалтын хэмжээг шалгахад)."""
    async with engine.begin() as connection:
        names = (
            await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'orders' AND column_name <> 'id' "
                    "AND is_generated = 'NEVER'"
                )
            )
        ).scalars()
        columns = list(names)
        values = [
            "'COPY-' || copy"
            if name == "number"
            else "'copy-' || copy"
            if name == "idempotency_key"
            else f"o.{name}"
            for name in columns
        ]
        await connection.execute(
            text(
                f"INSERT INTO orders ({', '.join(columns)}) "  # noqa: S608 - тестийн баганын нэр
                f"SELECT {', '.join(values)} FROM orders o, generate_series(1, :times) AS copy "
                "WHERE o.number = :number"
            ),
            {"times": times, "number": number},
        )


def test_money_is_written_in_whole_togrog_and_keeps_any_remainder() -> None:
    assert [money_cell(c) for c in (12_790_000, 150, 5, 0)] == [127_900, "1.50", "0.05", 0]


@pytest.mark.parametrize("cell", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx"])
def test_text_that_looks_like_a_formula_is_quoted(cell: str) -> None:
    assert safe_cell(cell) == "'" + cell


@pytest.mark.parametrize("cell", ["Болд", "a=b", 5, None])
def test_other_values_are_left_alone(cell: object) -> None:
    assert safe_cell(cell) == cell
