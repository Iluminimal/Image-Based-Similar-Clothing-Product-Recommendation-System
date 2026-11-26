"""Худалдан авагч харсан дүнгээсээ өөр дүнгээр захиалахгүй; нэг Idempotency-Key нь нэг л хүсэлт."""

import uuid

import pytest
from sqlalchemy import text

from tests.commerce.test_webhook_api import place_order
from tests.conftest import Api, ApiFactory
from tests.support.commerce import (
    Shopper,
    add_address,
    add_to_cart,
    checkout,
    register,
    set_product,
    stock_of,
)
from tests.support.fakes import RecordingGateway

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

PRICE_CHANGED = "urn:angel:problem:price-changed"
KEY_REUSED = "urn:angel:problem:idempotency-key-reused"


async def orders_made(api: Api) -> int:
    async with api.app.state.engine.connect() as connection:
        return int((await connection.execute(text("SELECT count(*) FROM orders"))).scalar_one())


async def shown_total(api: Api, shopper: Shopper) -> int:
    """Checkout хуудасны харуулдаг дүн: сагс + энгийн хүргэлт (босгоос дээш үнэгүй)."""
    subtotal = (await api.client.get("/api/v1/cart", headers=shopper.auth)).json()["subtotal_cents"]
    free = subtotal >= api.settings.free_shipping_threshold_cents
    return int(subtotal + (0 if free else api.settings.shipping_standard_ub_cents))


async def ready(api: Api) -> tuple[Shopper, int, int]:
    product = next(e for e in api.entries if e.in_stock and e.article_type != "Casual Shoes")
    await set_product(api.app.state.engine, product.product_id, price_cents=1_000_000)
    shopper = await register(api.client)
    await add_to_cart(api.client, product.product_id, size="M", token=shopper.token)
    return shopper, await add_address(shopper), product.product_id


async def test_a_price_change_stops_checkout_until_the_new_total_is_accepted(
    api_factory: ApiFactory,
) -> None:
    async with api_factory() as api:
        shopper, address, product = await ready(api)
        seen = await shown_total(api, shopper)
        stock = await stock_of(api.app.state.engine, product)
        await set_product(api.app.state.engine, product, price_cents=1_200_000)

        stale = await checkout(shopper, address, expected_total=seen)

        assert (stale.status_code, stale.json()["type"]) == (409, PRICE_CHANGED), stale.text
        assert stale.json()["total_cents"] == seen + 200_000
        assert await orders_made(api) == 0
        assert await stock_of(api.app.state.engine, product) == stock

        accepted = await checkout(shopper, address, expected_total=seen + 200_000)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["order"]["total_cents"] == seen + 200_000


async def test_a_refused_total_leaves_the_earlier_unpaid_order_and_its_invoice_alone(
    api_factory: ApiFactory,
) -> None:
    gateway = RecordingGateway(qpay=True)
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        await add_to_cart(
            api.client, placed.product_id, size="L", quantity=1, token=placed.shopper.token
        )

        stale = await checkout(placed.shopper, await add_address(placed.shopper), expected_total=1)

        assert stale.json()["type"] == PRICE_CHANGED, stale.text
        assert gateway.cancelled == []  # QR хүчинтэй хэвээр
        assert (await placed.order())["status"] == "pending"


async def test_one_key_cannot_be_reused_for_a_different_request(api_factory: ApiFactory) -> None:
    async with api_factory() as api:
        shopper, address, _ = await ready(api)
        other = await add_address(shopper, line1="Another street 5")
        key = uuid.uuid4().hex

        first = await checkout(shopper, address, key=key)
        replay = await checkout(shopper, address, key=key)
        different_address = await checkout(shopper, other, key=key)
        different_method = await checkout(shopper, address, key=key, method="pickup")

        assert first.status_code == replay.status_code == 200
        assert replay.json()["order"]["number"] == first.json()["order"]["number"]
        for response in (different_address, different_method):
            assert (response.status_code, response.json()["type"]) == (422, KEY_REUSED)
        assert await orders_made(api) == 1
