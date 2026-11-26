"""Төлсөн мөнгө хэзээ ч гацахгүй: мэдэгдэл (callback) алдагдсан ч сервер төлөгдсөнийг мэдсэн тэр
газраа захиалгыг шийднэ; буцаах ёстой мөнгө буцтал дахин оролдоно."""

import pytest
from sqlalchemy import text

from angel.services.commerce import expiry
from angel.services.commerce.expiry import OrderExpirer
from tests.admin.test_admin_orders_api import administrator
from tests.commerce.test_webhook_api import Placed, place_order
from tests.conftest import Api, ApiFactory
from tests.support.commerce import (
    Shopper,
    add_address,
    add_to_cart,
    another_client,
    checkout,
    qpay_callback,
    register,
    stock_of,
)
from tests.support.fakes import RecordingGateway

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]


@pytest.fixture
def gateway() -> RecordingGateway:
    return RecordingGateway(qpay=True)


def paid_without_notice(placed: Placed) -> None:
    """Төлсөн ч мэдэгдэл ирээгүй: provider цуцлахад "төлөгдсөн" гэнэ."""
    placed.gateway.pay(placed.intent_id, placed.charge)
    placed.gateway.cancel_outcome = "succeeded"


async def age_orders(api: Api, minutes: int = 120) -> None:
    async with api.app.state.engine.begin() as connection:
        await connection.execute(
            text("UPDATE orders SET created_at = now() - make_interval(mins => :m)"), {"m": minutes}
        )


def sweeper(api: Api, gateway: RecordingGateway) -> OrderExpirer:
    return OrderExpirer(api.app.state.sessions, gateway, api.settings)


async def event_types(api: Api, number: str) -> list[str]:
    async with api.app.state.engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT e.type FROM order_events e JOIN orders o ON o.id = e.order_id "
                "WHERE o.number = :n ORDER BY e.id"
            ),
            {"n": number},
        )
        return [row.type for row in rows]


async def test_the_expiry_sweep_completes_an_order_that_was_paid_without_a_notification(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        reserved = await placed.stock()
        paid_without_notice(placed)
        await age_orders(api)

        released = await sweeper(api, gateway).run_once()

        assert released == 0
        assert (await placed.order())["status"] == "paid"
        assert await placed.stock() == reserved


async def test_a_customer_cancelling_a_paid_order_completes_it_instead(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        paid_without_notice(placed)

        response = await api.client.post(
            f"/api/v1/orders/{placed.number}/cancel", headers=placed.shopper.auth
        )

        assert response.status_code == 409
        assert (await placed.order())["status"] == "paid"


async def test_an_administrator_cancelling_a_paid_order_completes_it_instead(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        paid_without_notice(placed)
        async with another_client(api) as client:
            admin = await administrator(
                Api(client, api.app, api.embedder, api.entries, api.settings),
                api.app.state.engine,
            )

            response = await client.post(
                f"/api/v1/admin/orders/{placed.number}/cancel", json={}, headers=admin.auth
            )

        assert response.status_code == 409
        assert (await placed.order())["status"] == "paid"


async def test_a_new_checkout_completes_the_old_order_that_turned_out_to_be_paid(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        paid_without_notice(placed)
        await add_to_cart(
            api.client, placed.product_id, size="M", quantity=1, token=placed.shopper.token
        )

        response = await checkout(placed.shopper, await add_address(placed.shopper))

        assert response.status_code == 409
        assert response.json()["type"] == "urn:angel:problem:payment-in-progress"
        assert (await placed.order())["status"] == "paid"


async def test_orders_that_cannot_be_closed_do_not_block_the_ones_behind_them(
    api_factory: ApiFactory, gateway: RecordingGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(expiry, "BATCH", 1)
    async with api_factory(gateway=gateway) as api:
        products = [e for e in api.entries if e.in_stock and e.article_type != "Casual Shoes"]
        numbers: list[str] = []
        buyers: list[Shopper] = []
        for product in products[:2]:
            shopper = await register(api.client)
            await add_to_cart(api.client, product.product_id, size="M", token=shopper.token)
            response = await checkout(shopper, await add_address(shopper))
            numbers.append(response.json()["order"]["number"])
            buyers.append(shopper)
        before = await stock_of(api.app.state.engine, products[1].product_id)
        # Эхнийх нь гацсан: provider "төлөгдсөн" гэх боловч төлбөрийг нь буцааж өгөхгүй.
        gateway.stuck.add(gateway.intents[0])
        await age_orders(api)

        released = await sweeper(api, gateway).run_once()

        assert released == 1
        assert await stock_of(api.app.state.engine, products[1].product_id) == before + 1


async def test_a_refund_the_provider_refuses_is_remembered_and_retried_by_the_sweep(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway) as api:
        placed = await place_order(api, gateway)
        await api.client.post(f"/api/v1/orders/{placed.number}/cancel", headers=placed.shopper.auth)
        gateway.fail_refund = True

        await placed.pay_and_notify(payment_id="late")

        owed = await placed.order()
        assert (await placed.payment())["status"] == "refund_pending"
        assert owed["refund_pending"] is True
        assert "refunded" not in await event_types(api, placed.number)

        await sweeper(api, gateway).run_once()  # provider унасан хэвээр: юу ч алдагдахгүй
        assert (await placed.payment())["status"] == "refund_pending"

        gateway.fail_refund = False
        await sweeper(api, gateway).run_once()
        await sweeper(api, gateway).run_once()

        assert (await placed.payment())["status"] == "refunded"
        assert gateway.refunds == [placed.intent_id]
        assert (await event_types(api, placed.number)).count("refunded") == 1
        assert (await placed.order())["refund_pending"] is False
        # Дахин ирсэн мэдэгдэл хоёр дахь удаа буцаахгүй.
        await qpay_callback(api.client, placed.number)
        assert gateway.refunds == [placed.intent_id]


async def test_a_failing_refund_is_not_hammered_every_minute(
    api_factory: ApiFactory, gateway: RecordingGateway
) -> None:
    async with api_factory(gateway=gateway, refund_retry_minutes=15) as api:
        placed = await place_order(api, gateway)
        await api.client.post(f"/api/v1/orders/{placed.number}/cancel", headers=placed.shopper.auth)
        gateway.fail_refund = True
        await placed.pay_and_notify(payment_id="late")
        gateway.fail_refund = False

        await sweeper(api, gateway).run_once()  # дөнгөж сая оролдсон: хүлээнэ
        assert gateway.refunds == []

        async with api.app.state.engine.begin() as connection:
            await connection.execute(
                text("UPDATE payments SET updated_at = now() - interval '16 minutes'")
            )
        await sweeper(api, gateway).run_once()

        assert gateway.refunds == [placed.intent_id]
        assert (await placed.payment())["status"] == "refunded"
