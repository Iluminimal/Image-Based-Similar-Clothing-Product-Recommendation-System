"""Account устгасны дараа тухайн хүний хувийн мэдээлэл үлдэх ёсгүй: устгах диалог хэрэглэгчид ингэж
амладаг."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.test_admin_orders_api import administrator, in_stock, place_order, warehouse_worker
from tests.conftest import Api, ApiFactory
from tests.support.commerce import PASSWORD, Shopper, register
from tests.support.fakes import RecordingGateway

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]


async def count(engine: AsyncEngine, sql: str, **params: object) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(text(sql), params)).scalar_one())


async def delete_account(api: Api, who: Shopper) -> None:
    response = await api.client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"confirm": who.email, "password": PASSWORD},
        headers=who.auth,
    )
    assert response.status_code == 204, response.text


async def test_deleting_an_account_forgets_where_and_how_the_person_signed_in(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        leaving = await register(api.client)
        staying = await register(api.client)
        for who in (leaving, staying):
            await api.client.post(
                "/api/v1/auth/login", json={"email": who.email, "password": PASSWORD}
            )
            # Нэвтрэх болон нууц үг сэргээх код: нэг нь бүртгэлийн id-гүй, зөвхөн хаягаар.
            await api.client.post("/api/v1/auth/password/forgot", json={"destination": who.email})

        await delete_account(api, leaving)

        events = "SELECT count(*) FROM security_events WHERE user_id = :u"
        codes = "SELECT count(*) FROM otp_challenges WHERE destination = :d"
        assert await count(db_engine, events, u=leaving.user_id) == 0
        assert await count(db_engine, codes, d=leaving.email) == 0
        assert await count(db_engine, events, u=staying.user_id) > 0
        assert await count(db_engine, codes, d=staying.email) > 0


async def test_deleting_an_account_removes_what_the_person_wrote_in_a_request(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path, gateway=RecordingGateway()) as api:
        admin = await administrator(api, db_engine)
        await warehouse_worker(api, db_engine)
        shopper, number = await place_order(api, in_stock(api, 0), pay=True)
        asked = await api.client.post(
            f"/api/v1/orders/{number}/requests",
            json={"kind": "cancel", "reason": "other", "details": "Би 99112233 руу залгана уу"},
            headers=shopper.auth,
        )
        request_id = asked.json()["requests"][0]["id"]
        approved = await api.client.post(
            f"/api/v1/admin/orders/{number}/requests/{request_id}/approve", headers=admin.auth
        )
        assert approved.status_code == 200, approved.text

        await delete_account(api, shopper)

        kept = "SELECT count(*) FROM order_requests WHERE reason = 'other'"
        written = "SELECT count(*) FROM order_requests WHERE details IS NOT NULL"
        assert await count(db_engine, kept) == 1  # бичлэг ба шалтгааны ангилал үлдэнэ
        assert await count(db_engine, written) == 0
        # Захиалга санхүүгийн бүртгэлд хэвээр.
        assert (
            await count(db_engine, "SELECT count(*) FROM orders WHERE number = :n", n=number) == 1
        )
