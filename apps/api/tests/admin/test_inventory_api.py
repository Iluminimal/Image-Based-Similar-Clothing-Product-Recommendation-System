"""Үлдэгдлийн тоолол: **боломжтой** (зарах боломжтой) + **захиалагдсан** (төлбөр хүлээж буй эсвэл
төлсөн, хараахан илгээгээгүй) = **агуулахад байгаа**. Агуулахын ажилтан тоолсон тоогоо оруулна."""

from pathlib import Path

import pytest
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.test_admin_orders_api import in_stock, place_order, warehouse_worker
from tests.conftest import Api, ApiFactory
from tests.support.commerce import Shopper, set_product, stock_of

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

PRODUCTS = "/api/v1/admin/products"
BELOW = "urn:angel:problem:stock-below-committed"


async def numbers(api: Api, worker: Shopper, product_id: int) -> tuple[int, int, int]:
    """(боломжтой, захиалагдсан, агуулахад байгаа)."""
    body = (await api.client.get(f"{PRODUCTS}/{product_id}", headers=worker.auth)).json()
    return body["stock_quantity"], body["committed"], body["on_hand"]


async def count_shelf(api: Api, worker: Shopper, product_id: int, on_hand: int) -> Response:
    return await api.client.put(
        f"{PRODUCTS}/{product_id}/stock", json={"on_hand": on_hand}, headers=worker.auth
    )


async def test_units_held_for_unshipped_orders_are_still_on_the_shelf(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        product = in_stock(api)
        await set_product(db_engine, product.product_id, stock_quantity=10)

        _, paid = await place_order(api, product, pay=True)
        assert await numbers(api, worker, product.product_id) == (8, 2, 10)
        await place_order(api, product)  # төлбөр хүлээж буй захиалга ч нөөц эзэлдэг
        assert await numbers(api, worker, product.product_id) == (6, 4, 10)

        shipped = await api.client.post(
            f"/api/v1/admin/orders/{paid}/ship",
            json={"carrier": "Монгол шуудан", "tracking_number": "MN1"},
            headers=worker.auth,
        )

        assert shipped.status_code == 200, shipped.text
        assert await numbers(api, worker, product.product_id) == (6, 2, 8)  # агуулахаас гарсан


async def test_counting_the_shelf_never_sells_units_that_are_already_sold(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        product = in_stock(api)
        await set_product(db_engine, product.product_id, stock_quantity=5)
        await place_order(api, product, pay=True)  # 2 ширхэг төлөгдсөн, агуулахдаа

        same = await count_shelf(api, worker, product.product_id, 5)
        assert (same.status_code, same.json()["stock_quantity"]) == (200, 3)
        more = await count_shelf(api, worker, product.product_id, 10)
        assert (more.status_code, more.json()["stock_quantity"]) == (200, 8)
        too_few = await count_shelf(api, worker, product.product_id, 1)

        assert (too_few.status_code, too_few.json()["type"]) == (409, BELOW)
        assert too_few.json()["committed"] == 2
        assert await stock_of(db_engine, product.product_id) == 8


async def test_editing_details_leaves_the_stock_alone(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        product = in_stock(api)
        await set_product(db_engine, product.product_id, stock_quantity=9)
        await place_order(api, product)
        url = f"{PRODUCTS}/{product.product_id}"

        renamed = await api.client.patch(url, json={"name": "New name"}, headers=worker.auth)
        assert (renamed.status_code, renamed.json()["stock_quantity"]) == (200, 7)
        counted = await api.client.patch(url, json={"on_hand": 6}, headers=worker.auth)
        assert (counted.status_code, counted.json()["stock_quantity"]) == (200, 4)
        below = await api.client.patch(url, json={"on_hand": 1}, headers=worker.auth)
        assert below.json()["type"] == BELOW
        # Хуучин талбар хүлээн авахгүй: "боломжтой" тоог шууд дарж бичих зам үлдээгүй.
        old = await api.client.patch(url, json={"stock_quantity": 50}, headers=worker.auth)
        assert old.status_code == 422


async def test_the_list_and_the_warehouse_board_show_all_three_numbers(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        product = in_stock(api)
        await set_product(db_engine, product.product_id, stock_quantity=4)
        await place_order(api, product, pay=True)

        listed = await api.client.get(
            PRODUCTS, params={"q": str(product.product_id)}, headers=worker.auth
        )
        board = await api.client.get("/api/v1/admin/fulfillment", headers=worker.auth)

        row = next(p for p in listed.json()["items"] if p["id"] == product.product_id)
        assert (row["stock_quantity"], row["committed"], row["on_hand"]) == (2, 2, 4)
        alert = next(p for p in board.json()["stock_alerts"] if p["id"] == product.product_id)
        assert (alert["stock_quantity"], alert["committed"], alert["on_hand"]) == (2, 2, 4)
