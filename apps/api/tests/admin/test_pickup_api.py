"""Дэлгүүрээс авах захиалга тээврийн компанигүй: "илгээх" нь **авахад бэлэн**, "хүргэх" нь
**авсан** гэсэн үг. Төлөв нь ижил (`shipped`, `delivered`)."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.test_admin_orders_api import in_stock, warehouse_worker
from tests.conftest import Api, ApiFactory
from tests.support.commerce import Shopper, add_address, add_to_cart, checkout, register
from tests.support.fakes import RecordingMailer
from tests.support.mail import deliver_mail

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

ADMIN = "/api/v1/admin/orders"
CARRIER = {"carrier": "Монгол шуудан", "tracking_number": "MN123"}


async def paid_order(api: Api, method: str, skip: int = 0) -> tuple[Shopper, str]:
    shopper = await register(api.client)
    await add_to_cart(api.client, in_stock(api, skip).product_id, token=shopper.token)
    placed = await checkout(shopper, await add_address(shopper), method=method)
    assert placed.status_code == 200, placed.text
    number = placed.json()["order"]["number"]
    paid = await api.client.post(
        f"/api/v1/checkout/orders/{number}/simulate-payment", headers=shopper.auth
    )
    assert paid.status_code == 200, paid.text
    return shopper, number


async def test_a_pickup_order_is_made_ready_without_a_carrier_and_then_collected(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        shopper, number = await paid_order(api, "pickup")
        await deliver_mail(api)  # бүртгэл, төлбөрийн имэйл энд хамаарахгүй
        mailer = RecordingMailer()
        api.app.state.mailer = mailer

        ready = await api.client.post(f"{ADMIN}/{number}/ship", json={}, headers=worker.auth)
        collected = await api.client.post(f"{ADMIN}/{number}/deliver", headers=worker.auth)

        assert ready.status_code == 200, ready.text
        body = ready.json()
        assert (body["status"], body["carrier"], body["tracking_number"]) == ("shipped", None, None)
        assert collected.json()["status"] == "delivered"
        await deliver_mail(api)
        ready_mail, collected_mail = mailer.sent
        assert "авахад бэлэн" in ready_mail.subject
        assert api.settings.pickup_address in ready_mail.body
        assert "Илгээмжийн дугаар" not in ready_mail.body
        assert "авлаа" in collected_mail.subject
        listed = (await api.client.get("/api/v1/orders", headers=shopper.auth)).json()
        admin_listed = (await api.client.get(ADMIN, headers=worker.auth)).json()
        assert listed["items"][0]["shipping_method"] == "pickup"
        assert admin_listed["items"][0]["shipping_method"] == "pickup"


async def test_a_carrier_belongs_to_deliveries_only(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path) as api:
        worker = await warehouse_worker(api, db_engine)
        _, pickup = await paid_order(api, "pickup", 0)
        _, delivery = await paid_order(api, "standard", 1)

        pickup_with_carrier = await api.client.post(
            f"{ADMIN}/{pickup}/ship", json=CARRIER, headers=worker.auth
        )
        nothing = await api.client.post(f"{ADMIN}/{delivery}/ship", json={}, headers=worker.auth)
        half = await api.client.post(
            f"{ADMIN}/{delivery}/ship", json={"carrier": "Монгол шуудан"}, headers=worker.auth
        )
        full = await api.client.post(f"{ADMIN}/{delivery}/ship", json=CARRIER, headers=worker.auth)

        assert [r.status_code for r in (pickup_with_carrier, nothing, half)] == [422, 422, 422]
        assert full.status_code == 200, full.text
