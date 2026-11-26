"""Бараа устгах ба жагсаалтын нэмэлт мэдээлэл. Хэзээ ч захиалагдаагүй барааг л бүрмөсөн устгана:
захиалгын мөр бараа руугаа заадаг."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from angel.ingestion.images import THUMBNAIL_SIZES, thumbnail_key
from angel.repositories.commerce.orders import OrderRepository
from tests.admin.test_admin_orders_api import administrator, place_order
from tests.admin.test_admin_products_api import (
    NOT_FOUND,
    PRODUCTS,
    admin_api,
    create,
    media_files,
    search_ids,
)
from tests.conftest import Api, ApiFactory
from tests.support.catalogue import make_jpeg
from tests.support.commerce import Shopper, add_to_cart, register

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

HAS_ORDERS = "urn:angel:problem:product-has-orders"


async def count(engine: AsyncEngine, sql: str, **params: Any) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(text(sql), params)).scalar_one())


async def listing(api: Api, staff: Shopper, **params: Any) -> dict[str, Any]:
    response = await api.client.get(
        PRODUCTS, params={"page_size": 100, **params}, headers=staff.auth
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_a_product_nobody_ordered_is_removed_with_everything_that_held_it(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        made = await create(api, worker, seed=901)
        product_id = made.json()["id"]
        shopper = await register(api.client)
        await add_to_cart(shopper.client, product_id, token=shopper.token)
        saved = await shopper.client.put(f"/api/v1/wishlist/{product_id}", headers=shopper.auth)
        assert saved.status_code == 204, saved.text
        assert media_files(tmp_path)
        assert product_id in await search_ids(api, make_jpeg(901))
        listed = await api.client.get("/api/v1/products", params={"page_size": 60})
        assert product_id in [item["id"] for item in listed.json()["items"]]

        response = await api.client.delete(f"{PRODUCTS}/{product_id}", headers=worker.auth)

        assert response.status_code == 204, response.text
        gone = await api.client.get(f"{PRODUCTS}/{product_id}", headers=worker.auth)
        assert (gone.status_code, gone.json()["type"]) == (404, NOT_FOUND)
        assert (await api.client.get(f"/api/v1/products/{product_id}")).status_code == 404
        assert product_id not in await search_ids(api, make_jpeg(901))
        listed = await api.client.get("/api/v1/products", params={"page_size": 60})
        assert product_id not in [item["id"] for item in listed.json()["items"]]
        for table in ("cart_items", "wishlist_items"):
            left = await count(
                db_engine,
                f"SELECT count(*) FROM {table} WHERE product_id = :id",  # noqa: S608 - тест
                id=product_id,
            )
            assert left == 0, table
        assert media_files(tmp_path) == []
        entry = await count(
            db_engine,
            "SELECT count(*) FROM staff_audit_log WHERE action = 'product.delete' "
            "AND entity_id = :id AND data ->> 'name' = 'Linen camp shirt'",
            id=str(product_id),
        )
        assert entry == 1


async def test_pictures_that_came_from_the_dataset_are_left_on_disk(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    """Зураг солихтой ижил дүрэм: админ самбар зөвхөн өөрийн upload хийсэн файлыг устгана."""
    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        product_id = api.entries[1].product_id
        async with db_engine.connect() as connection:
            key = (
                await connection.execute(
                    text("SELECT image_key FROM products WHERE id = :id"), {"id": product_id}
                )
            ).scalar_one()
        files = [tmp_path / thumbnail_key(key, size) for size in THUMBNAIL_SIZES]
        for file in files:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"dataset thumbnail")

        response = await api.client.delete(f"{PRODUCTS}/{product_id}", headers=worker.auth)

        assert response.status_code == 204, response.text
        assert all(file.exists() for file in files)


@pytest.mark.parametrize("pay", [True, False], ids=["paid order", "unpaid order"])
async def test_a_product_that_was_ordered_is_kept(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path, pay: bool
) -> None:
    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        product = api.entries[1]  # нөөцтэй
        await place_order(api, product, pay=pay)

        response = await api.client.delete(f"{PRODUCTS}/{product.product_id}", headers=worker.auth)

        assert response.status_code == 409, response.text
        assert response.json()["type"] == HAS_ORDERS
        kept = await api.client.get(f"{PRODUCTS}/{product.product_id}", headers=worker.auth)
        assert (kept.status_code, kept.json()["ordered"]) == (200, True)


async def test_an_order_placed_while_deleting_is_still_protected(
    api_factory: ApiFactory,
    db_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Шалгалтыг алгассан ч өгөгдлийн сангийн `RESTRICT` хамгаална: 500 биш, мөн л 409."""

    async def nothing(self: OrderRepository, product_ids: list[int]) -> set[int]:
        return set()

    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        product = api.entries[1]
        await place_order(api, product, pay=True)
        monkeypatch.setattr(OrderRepository, "ordered_product_ids", nothing)

        response = await api.client.delete(f"{PRODUCTS}/{product.product_id}", headers=worker.auth)

        assert response.status_code == 409, response.text
        assert response.json()["type"] == HAS_ORDERS


async def test_only_the_warehouse_may_delete(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        product_id = (await create(api, worker, seed=902)).json()["id"]
        admin = await administrator(api, db_engine)
        customer = await register(api.client)

        statuses = [
            (await api.client.delete(f"{PRODUCTS}/{product_id}", headers=headers)).status_code
            for headers in ({}, customer.auth, admin.auth)
        ]

        assert statuses == [401, 403, 403]
        assert (
            await api.client.get(f"{PRODUCTS}/{product_id}", headers=worker.auth)
        ).status_code == 200
        missing = await api.client.delete(f"{PRODUCTS}/999999", headers=worker.auth)
        assert (missing.status_code, missing.json()["type"]) == (404, NOT_FOUND)


async def test_the_list_says_which_products_were_ordered_and_counts_each_status(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with admin_api(api_factory, db_engine, tmp_path) as (api, worker):
        ordered, stopped = api.entries[1], api.entries[2]
        await place_order(api, ordered, pay=True)
        await api.client.post(f"{PRODUCTS}/{stopped.product_id}/deactivate", headers=worker.auth)

        everything = await listing(api, worker)
        only_stopped = await listing(api, worker, status="inactive")
        searched = await listing(api, worker, q=str(stopped.product_id))

        flags = {item["id"]: item["ordered"] for item in everything["items"]}
        assert flags[ordered.product_id] is True
        assert flags[stopped.product_id] is False
        total = len(api.entries)
        expected = {"all": total, "active": total - 1, "inactive": 1}
        assert everything["status_counts"] == expected
        # Тоо нь сонгосон табаас хамаарахгүй, харин хайлт ба нөөцийн шүүлтүүрийг дагана.
        assert only_stopped["status_counts"] == expected
        assert only_stopped["total"] == 1
        assert searched["status_counts"]["inactive"] == 1
        assert searched["status_counts"]["all"] == searched["total"]
