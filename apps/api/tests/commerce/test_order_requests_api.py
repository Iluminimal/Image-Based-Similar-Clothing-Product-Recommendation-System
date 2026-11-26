"""Борлуулалтын дараах үйлчилгээ: илгээгээгүй захиалгыг цуцлах, хүргэгдсэн захиалгыг буцаах
хүсэлт, ажилтны шийдвэр, мөнгө ба нөөц яг нэг удаа буцах."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.test_admin_orders_api import administrator, warehouse_worker
from tests.commerce.test_order_fulfillment_api import ADMIN, INVALID, SHIP, Shop, event_types
from tests.conftest import ApiFactory
from tests.support.commerce import PASSWORD, Shopper, register, stock_of
from tests.support.fakes import RecordingGateway, RecordingMailer

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

NOT_ALLOWED = "urn:angel:problem:order-request-not-allowed"
ALREADY_OPEN = "urn:angel:problem:order-request-open"
QUANTITY = 2  # `place_order` барааг хоёр ширхэгээр захиалдаг


@pytest.fixture
async def shop(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> AsyncIterator[Shop]:
    gateway = RecordingGateway()
    async with api_factory(media_dir=tmp_path, gateway=gateway) as api:
        mailer = RecordingMailer()
        api.app.state.mailer = mailer
        yield Shop(
            api,
            await administrator(api, db_engine),
            await warehouse_worker(api, db_engine),
            gateway,
            mailer,
        )


async def delivered(shop: Shop) -> tuple[Shopper, str, int]:
    customer, number, product_id = await shop.order()
    assert (await shop.act(number, "ship", **SHIP)).status_code == 200
    assert (await shop.act(number, "deliver")).status_code == 200
    return customer, number, product_id


async def ask(
    shop: Shop,
    who: Shopper,
    number: str,
    kind: str = "cancel",
    reason: str = "changed_mind",
    **extra: object,
) -> Response:
    return await shop.api.client.post(
        f"/api/v1/orders/{number}/requests",
        json={"kind": kind, "reason": reason, **extra},
        headers=who.auth,
    )


async def asked(shop: Shop, who: Shopper, number: str, kind: str = "cancel") -> int:
    reason = "changed_mind" if kind == "cancel" else "wrong_size"
    response = await ask(shop, who, number, kind, reason)
    assert response.status_code == 200, response.text
    return int(response.json()["requests"][-1]["id"])


async def view(shop: Shop, who: Shopper, number: str) -> dict[str, Any]:
    response = await shop.api.client.get(f"/api/v1/orders/{number}", headers=who.auth)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def withdraw(shop: Shop, who: Shopper, number: str, request_id: int) -> Response:
    return await shop.api.client.post(
        f"/api/v1/orders/{number}/requests/{request_id}/withdraw", headers=who.auth
    )


async def decide(
    shop: Shop,
    number: str,
    request_id: int,
    action: str,
    *,
    by: Shopper | None = None,
    **body: object,
) -> Response:
    """Зөвшөөрөх, татгалзах нь админых; барааг хүлээн авах нь агуулахынх."""
    actor = by or (shop.worker if action == "receive" else shop.admin)
    return await shop.api.client.post(
        f"{ADMIN}/{number}/requests/{request_id}/{action}",
        json=body or None,
        headers=actor.auth,
    )


async def age_delivery(engine: AsyncEngine, number: str, by: timedelta) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE orders SET delivered_at = delivered_at - cast(:by AS interval) "
                "WHERE number = :number"
            ),
            {"by": by, "number": number},
        )


def statuses(order: dict[str, Any]) -> list[tuple[str, str]]:
    return [(r["kind"], r["status"]) for r in order["requests"]]


# --- хэзээ ямар хүсэлт гаргаж болох -----------------------------------------------------------


async def test_each_stage_of_an_order_offers_only_what_applies_to_it(shop: Shop) -> None:
    customer, number, _ = await shop.order(pay=False)
    unpaid = await view(shop, customer, number)
    assert unpaid["available_request"] is None
    assert (await ask(shop, customer, number)).json()["type"] == NOT_ALLOWED

    customer, number, _ = await shop.order(skip=1)
    paid = await view(shop, customer, number)
    assert (paid["available_request"], paid["return_deadline"]) == ("cancel", None)
    assert (await ask(shop, customer, number, "return", "wrong_size")).status_code == 409

    await shop.act(number, "ship", **SHIP)
    on_the_way = await view(shop, customer, number)
    assert on_the_way["available_request"] is None
    for kind, reason in (("cancel", "changed_mind"), ("return", "wrong_size")):
        assert (await ask(shop, customer, number, kind, reason)).json()["type"] == NOT_ALLOWED

    await shop.act(number, "deliver")
    arrived = await view(shop, customer, number)
    assert arrived["available_request"] == "return"
    assert arrived["return_deadline"] is not None
    assert (await ask(shop, customer, number)).status_code == 409


async def test_a_return_can_be_asked_for_until_the_window_closes(
    shop: Shop, db_engine: AsyncEngine
) -> None:
    customer, number, _ = await delivered(shop)
    await age_delivery(db_engine, number, timedelta(days=13, hours=23))
    assert (await view(shop, customer, number))["available_request"] == "return"

    await age_delivery(db_engine, number, timedelta(hours=2))
    late = await ask(shop, customer, number, "return", "wrong_size")

    assert (await view(shop, customer, number))["available_request"] is None
    assert late.status_code == 409
    assert late.json()["type"] == NOT_ALLOWED


async def test_the_return_window_is_a_setting(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    gateway = RecordingGateway()
    async with api_factory(media_dir=tmp_path, gateway=gateway, return_window_days=30) as api:
        shop = Shop(
            api,
            await administrator(api, db_engine),
            await warehouse_worker(api, db_engine),
            gateway,
            RecordingMailer(),
        )
        customer, number, _ = await delivered(shop)
        await age_delivery(db_engine, number, timedelta(days=20))

        response = await ask(shop, customer, number, "return", "defective")

        assert response.status_code == 200, response.text


async def test_asking_records_it_and_tells_the_customer_but_moves_no_money(
    shop: Shop, db_engine: AsyncEngine
) -> None:
    customer, number, product_id = await shop.order()
    stock = await stock_of(db_engine, product_id)

    response = await ask(shop, customer, number, "cancel", "too_slow", details="  Яарч байна  ")

    body = response.json()
    assert response.status_code == 200, response.text
    assert body["status"] == "paid"
    assert statuses(body) == [("cancel", "requested")]
    assert body["requests"][0]["reason"] == "too_slow"
    assert body["requests"][0]["details"] == "Яарч байна"
    assert body["available_request"] is None
    assert event_types(body)[-1] == "cancel_requested"
    assert shop.gateway.refunds == []
    assert await stock_of(db_engine, product_id) == stock
    [email] = [m for m in (await shop.mail()) if "хүсэлтийг хүлээн авлаа" in m.subject]
    assert email.to == customer.email


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "cancel", "reason": "wrong_size"},
        {"kind": "cancel", "reason": "other"},
        {"kind": "cancel", "reason": "other", "details": "   "},
        {"kind": "exchange", "reason": "changed_mind"},
        {"kind": "cancel", "reason": "changed_mind", "details": "x" * 501},
        {"kind": "cancel", "reason": "changed_mind", "restock": True},
    ],
)
async def test_a_request_needs_a_reason_that_fits(shop: Shop, body: dict[str, object]) -> None:
    customer, number, _ = await shop.order()

    response = await shop.api.client.post(
        f"/api/v1/orders/{number}/requests", json=body, headers=customer.auth
    )

    assert response.status_code == 422, response.text


async def test_only_the_owner_can_ask_or_take_back(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    request_id = await asked(shop, customer, number)
    stranger = await register(shop.api.client)

    anonymous = await shop.api.client.post(
        f"/api/v1/orders/{number}/requests", json={"kind": "cancel", "reason": "changed_mind"}
    )

    assert anonymous.status_code == 401
    assert (await ask(shop, stranger, number)).status_code == 404
    assert (await withdraw(shop, stranger, number, request_id)).status_code == 404
    assert statuses(await view(shop, customer, number)) == [("cancel", "requested")]


async def test_one_request_at_a_time_and_a_withdrawn_one_can_be_made_again(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    first = await asked(shop, customer, number)

    again = await ask(shop, customer, number)
    taken_back = await withdraw(shop, customer, number, first)

    assert again.json()["type"] == ALREADY_OPEN
    assert taken_back.status_code == 200, taken_back.text
    assert statuses(taken_back.json()) == [("cancel", "withdrawn")]
    assert taken_back.json()["available_request"] == "cancel"
    assert (await withdraw(shop, customer, number, first)).json()["type"] == INVALID
    await asked(shop, customer, number)


async def test_two_requests_at_once_create_one(shop: Shop) -> None:
    customer, number, _ = await shop.order()

    responses = await asyncio.gather(*(ask(shop, customer, number) for _ in range(3)))

    assert sorted(r.status_code for r in responses) == [200, 409, 409]
    assert statuses(await view(shop, customer, number)) == [("cancel", "requested")]


# --- цуцлах хүсэлт ----------------------------------------------------------------------------


async def test_an_order_with_an_open_cancellation_is_not_shipped(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    request_id = await asked(shop, customer, number)

    blocked = await shop.act(number, "ship", **SHIP)
    await decide(shop, number, request_id, "decline", note="Аль хэдийн баглачихсан байна")
    shipped = await shop.act(number, "ship", **SHIP)

    assert blocked.status_code == 409
    assert blocked.json()["type"] == ALREADY_OPEN
    assert shipped.status_code == 200, shipped.text


async def test_approving_a_cancellation_refunds_and_restocks_exactly_once(
    shop: Shop, db_engine: AsyncEngine
) -> None:
    customer, number, product_id = await shop.order()
    stock = await stock_of(db_engine, product_id)
    request_id = await asked(shop, customer, number)

    response = await decide(shop, number, request_id, "approve", note="Уучлаарай, удсан байна")
    repeated = await decide(shop, number, request_id, "approve")

    body = response.json()
    assert response.status_code == 200, response.text
    assert (body["status"], body["payment"]["status"]) == ("refunded", "refunded")
    assert statuses(body) == [("cancel", "completed")]
    assert event_types(body)[-2:] == ["request_approved", "refunded"]
    assert body["events"][-1]["data"]["reason"] == "cancel_request"
    assert repeated.json()["type"] == INVALID
    assert len(shop.gateway.refunds) == 1
    assert await stock_of(db_engine, product_id) == stock + QUANTITY
    [email] = [m for m in (await shop.mail()) if "буцаагдлаа" in m.subject]
    assert "Уучлаарай, удсан байна" in email.body
    audit = (await shop.api.client.get("/api/v1/admin/audit", headers=shop.admin.auth)).json()
    assert {"order.approve", "order.refund"} <= {e["action"] for e in audit["items"]}


async def test_a_refused_refund_leaves_the_cancellation_waiting(
    shop: Shop, db_engine: AsyncEngine
) -> None:
    customer, number, product_id = await shop.order()
    stock = await stock_of(db_engine, product_id)
    request_id = await asked(shop, customer, number)
    shop.gateway.fail_refund = True

    response = await decide(shop, number, request_id, "approve")

    assert response.status_code == 502
    body = await shop.get(number)
    assert (body["status"], statuses(body)) == ("paid", [("cancel", "requested")])
    assert event_types(body)[-1] == "cancel_requested"
    assert await stock_of(db_engine, product_id) == stock

    shop.gateway.fail_refund = False
    assert (await decide(shop, number, request_id, "approve")).status_code == 200
    assert await stock_of(db_engine, product_id) == stock + QUANTITY


async def test_declining_needs_a_reason_the_customer_can_read(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    request_id = await asked(shop, customer, number)

    silent = await decide(shop, number, request_id, "decline")
    response = await decide(shop, number, request_id, "decline", note="Илгээхээр бэлдсэн")

    assert silent.status_code == 422
    assert response.status_code == 200, response.text
    seen = await view(shop, customer, number)
    assert statuses(seen) == [("cancel", "declined")]
    assert seen["requests"][0]["decision_note"] == "Илгээхээр бэлдсэн"
    assert seen["events"][-1]["data"] == {"kind": "cancel"}
    assert shop.admin.email not in str(seen)
    assert seen["available_request"] is None
    assert (await ask(shop, customer, number)).json()["type"] == NOT_ALLOWED
    [email] = [m for m in (await shop.mail()) if "зөвшөөрөх боломжгүй" in m.subject]
    assert "Илгээхээр бэлдсэн" in email.body


async def test_a_declined_cancellation_does_not_take_away_the_later_return(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    request_id = await asked(shop, customer, number)
    await decide(shop, number, request_id, "decline", note="Илгээхээр бэлдсэн")
    await shop.act(number, "ship", **SHIP)
    await shop.act(number, "deliver")

    assert (await view(shop, customer, number))["available_request"] == "return"


# --- буцаах хүсэлт ----------------------------------------------------------------------------


async def test_a_return_is_approved_received_and_then_refunded(
    shop: Shop, db_engine: AsyncEngine
) -> None:
    customer, number, product_id = await delivered(shop)
    stock = await stock_of(db_engine, product_id)
    request_id = await asked(shop, customer, number, "return")

    approved = await decide(shop, number, request_id, "approve", note="Шошготой нь авчирна уу")
    instructions = await view(shop, customer, number)

    assert approved.status_code == 200, approved.text
    assert (approved.json()["status"], statuses(approved.json())) == (
        "delivered",
        [("return", "approved")],
    )
    assert instructions["return_address"] == shop.api.settings.pickup_address
    assert shop.gateway.refunds == []
    [email] = [m for m in (await shop.mail()) if "зөвшөөрөгдлөө" in m.subject]
    assert shop.api.settings.pickup_address in email.body
    assert "Шошготой нь авчирна уу" in email.body

    received = await decide(shop, number, request_id, "receive", restock=True)
    twice = await decide(shop, number, request_id, "receive", restock=True)

    assert received.status_code == 200, received.text
    assert statuses(received.json()) == [("return", "received")]
    assert received.json()["requests"][0]["restocked"] is True
    assert twice.json()["type"] == INVALID
    assert shop.gateway.refunds == []
    assert await stock_of(db_engine, product_id) == stock + QUANTITY
    assert (await view(shop, customer, number))["return_address"] is None

    again = await shop.act(number, "refund", reason="Буцаалт", restock=True)
    refund = await shop.act(number, "refund", reason="Буцаалт", restock=False)

    assert again.status_code == 409  # нөөцөд хоёр дахь удаагаа нэмэхгүй
    assert refund.status_code == 200, refund.text
    assert statuses(refund.json()) == [("return", "completed")]
    assert len(shop.gateway.refunds) == 1
    assert await stock_of(db_engine, product_id) == stock + QUANTITY
    assert event_types(refund.json())[-4:] == [
        "return_requested",
        "request_approved",
        "return_received",
        "refunded",
    ]


async def test_damaged_goods_stay_out_of_stock(shop: Shop, db_engine: AsyncEngine) -> None:
    customer, number, product_id = await delivered(shop)
    stock = await stock_of(db_engine, product_id)
    request_id = await asked(shop, customer, number, "return")
    await decide(shop, number, request_id, "approve")

    response = await decide(shop, number, request_id, "receive", restock=False)

    assert response.json()["requests"][0]["restocked"] is False
    assert (await shop.act(number, "refund", reason="x", restock=True)).status_code == 409
    assert await stock_of(db_engine, product_id) == stock


async def test_goods_cannot_be_received_before_the_return_is_approved(shop: Shop) -> None:
    customer, number, _ = await delivered(shop)
    request_id = await asked(shop, customer, number, "return")

    early = await decide(shop, number, request_id, "receive", restock=True)

    assert early.status_code == 409
    assert early.json()["type"] == INVALID


async def test_an_approved_return_whose_goods_never_come_can_be_closed(shop: Shop) -> None:
    customer, number, _ = await delivered(shop)
    request_id = await asked(shop, customer, number, "return")
    await decide(shop, number, request_id, "approve")

    too_late_to_withdraw = await withdraw(shop, customer, number, request_id)
    closed = await decide(shop, number, request_id, "decline", note="Бараа ирээгүй")

    assert too_late_to_withdraw.status_code == 409
    assert statuses(closed.json()) == [("return", "declined")]
    assert (await view(shop, customer, number))["return_address"] is None


async def test_goods_already_received_cannot_be_declined(shop: Shop) -> None:
    customer, number, _ = await delivered(shop)
    request_id = await asked(shop, customer, number, "return")
    await decide(shop, number, request_id, "approve")
    await decide(shop, number, request_id, "receive", restock=True)

    response = await decide(shop, number, request_id, "decline", note="Үгүй")

    assert response.status_code == 409


# --- эрх, хуучирсан дэлгэц, шууд төлбөр буцаалт -----------------------------------------------


async def test_each_decision_belongs_to_one_role(shop: Shop) -> None:
    customer, number, _ = await delivered(shop)
    request_id = await asked(shop, customer, number, "return")

    for action, body, wrong in (
        ("approve", {}, (shop.worker, customer)),
        ("decline", {"note": "x"}, (shop.worker, customer)),
        ("receive", {"restock": True}, (shop.admin, customer)),
    ):
        for actor in wrong:
            response = await decide(shop, number, request_id, action, by=actor, **body)
            assert response.status_code == 403, (action, actor.email)


async def test_a_decision_on_an_outdated_request_does_not_touch_the_new_one(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    old = await asked(shop, customer, number)
    await withdraw(shop, customer, number, old)
    await asked(shop, customer, number)

    response = await decide(shop, number, old, "approve")

    assert response.json()["type"] == INVALID
    assert shop.gateway.refunds == []
    assert statuses(await shop.get(number)) == [("cancel", "withdrawn"), ("cancel", "requested")]


async def test_a_direct_refund_settles_the_waiting_request(shop: Shop) -> None:
    customer, number, _ = await shop.order()
    await asked(shop, customer, number)

    response = await shop.act(number, "refund", reason="Бараа дууссан", restock=True)

    assert response.status_code == 200, response.text
    assert statuses(response.json()) == [("cancel", "completed")]
    assert (await view(shop, customer, number))["available_request"] is None


@pytest.mark.parametrize("attempt", range(6))
async def test_shipping_and_asking_to_cancel_at_once_never_both_win(
    shop: Shop, attempt: int
) -> None:
    customer, number, _ = await shop.order()

    shipped, request = await asyncio.gather(
        shop.act(number, "ship", **SHIP), ask(shop, customer, number)
    )

    order = await shop.get(number)
    assert sorted([shipped.status_code, request.status_code]) == [200, 409]
    if shipped.status_code == 200:
        assert (order["status"], order["requests"]) == ("shipped", [])
    else:
        assert (order["status"], statuses(order)) == ("paid", [("cancel", "requested")])


@pytest.mark.parametrize("attempt", range(4))
async def test_approving_and_withdrawing_at_once_never_refund_a_withdrawn_request(
    shop: Shop, attempt: int
) -> None:
    customer, number, _ = await shop.order()
    request_id = await asked(shop, customer, number)

    approved, taken_back = await asyncio.gather(
        decide(shop, number, request_id, "approve"), withdraw(shop, customer, number, request_id)
    )

    order = await shop.get(number)
    assert sorted([approved.status_code, taken_back.status_code]) == [200, 409]
    if approved.status_code == 200:
        assert (order["status"], statuses(order)) == ("refunded", [("cancel", "completed")])
    else:
        assert (order["status"], shop.gateway.refunds) == ("paid", [])


# --- ажилтны харагдац --------------------------------------------------------------------------


async def test_staff_can_find_what_waits_for_them(shop: Shop) -> None:
    cancelling, cancel_number, _ = await shop.order()
    await asked(shop, cancelling, cancel_number)
    returning, return_number, _ = await delivered(shop)
    return_id = await asked(shop, returning, return_number, "return")
    _, quiet, _ = await shop.order(skip=2)

    listed = (
        await shop.api.client.get(ADMIN, params={"status": "requests"}, headers=shop.admin.auth)
    ).json()
    stats = (await shop.api.client.get("/api/v1/admin/stats", headers=shop.admin.auth)).json()
    board = (
        await shop.api.client.get("/api/v1/admin/fulfillment", headers=shop.worker.auth)
    ).json()

    assert {o["number"] for o in listed["items"]} == {cancel_number, return_number}
    assert listed["open_requests"] == 2
    assert listed["status_counts"] == {"paid": 2, "delivered": 1}
    assert {o["number"]: o["open_request"] for o in listed["items"]}[return_number] == {
        "kind": "return",
        "status": "requested",
    }
    assert (stats["requests_to_handle"], stats["returns_to_handle"]) == (2, 1)
    assert {q["number"]: q["cancel_requested"] for q in board["queue"]} == {
        cancel_number: True,
        quiet: False,
    }
    assert board["returns_expected"] == []

    await decide(shop, return_number, return_id, "approve")
    stats = (await shop.api.client.get("/api/v1/admin/stats", headers=shop.admin.auth)).json()
    board = (
        await shop.api.client.get("/api/v1/admin/fulfillment", headers=shop.worker.auth)
    ).json()

    assert (stats["requests_to_handle"], stats["returns_to_handle"]) == (1, 0)
    assert [r["number"] for r in board["returns_expected"]] == [return_number]
    assert board["returns_expected_total"] == 1
    assert board["returns_expected"][0]["item_count"] == QUANTITY

    await decide(shop, return_number, return_id, "receive", restock=True)
    stats = (await shop.api.client.get("/api/v1/admin/stats", headers=shop.admin.auth)).json()

    assert (stats["requests_to_handle"], stats["returns_to_handle"]) == (2, 1)


async def test_an_account_with_an_unsettled_return_cannot_be_deleted(shop: Shop) -> None:
    customer, number, _ = await delivered(shop)
    request_id = await asked(shop, customer, number, "return")

    async def delete_account() -> Response:
        return await shop.api.client.request(
            "DELETE",
            "/api/v1/auth/me",
            json={"confirm": customer.email, "password": PASSWORD},
            headers=customer.auth,
        )

    blocked = await delete_account()
    await withdraw(shop, customer, number, request_id)
    gone = await delete_account()

    assert blocked.status_code == 409
    assert blocked.json()["type"] == "urn:angel:problem:open-orders"
    assert gone.status_code == 204, gone.text


async def test_asking_too_often_is_slowed_down(api_factory: ApiFactory, tmp_path: Path) -> None:
    async with api_factory(
        seed_count=5, media_dir=tmp_path, rate_limit_order_request="2/60"
    ) as api:
        shopper = await register(api.client)
        codes = [
            (
                await api.client.post(
                    "/api/v1/orders/LK-ABCD2345/requests",
                    json={"kind": "cancel", "reason": "changed_mind"},
                    headers=shopper.auth,
                )
            ).status_code
            for _ in range(3)
        ]

        assert codes == [404, 404, 429]
