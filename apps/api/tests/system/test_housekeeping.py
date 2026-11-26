"""Хугацаа нь өнгөрсөн өгөгдөл устаж, хэрэгтэй нь үлдэнэ."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from angel.services.system import housekeeping
from angel.services.system.housekeeping import Housekeeper
from tests.accounts.test_security_events_api import CHROME_MAC, SAFARI_IPHONE, login
from tests.conftest import Api, ApiFactory
from tests.support.commerce import register

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

REFRESH = "/api/v1/auth/refresh"


async def run(api: Api) -> dict[str, int]:
    return await Housekeeper(api.app.state.sessions, api.settings).run_once()


async def count(engine: AsyncEngine, table: str, where: str = "true") -> int:
    async with engine.connect() as connection:
        return int(
            (
                await connection.execute(text(f"SELECT count(*) FROM {table} WHERE {where}"))  # noqa: S608
            ).scalar_one()
        )


async def execute(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def age(engine: AsyncEngine, table: str, column: str, by: timedelta, where: str) -> None:
    await execute(
        engine,
        f"UPDATE {table} SET {column} = {column} - cast(:by AS interval) WHERE {where}",  # noqa: S608
        by=by,
    )


async def test_nothing_recent_is_touched(api_factory: ApiFactory, db_engine: AsyncEngine) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        await login(api, shopper.email)
        await api.client.post("/api/v1/auth/password/forgot", json={"destination": shopper.email})

        removed = await run(api)

    assert set(removed.values()) == {0}


async def test_one_time_codes_go_after_a_day(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        for address in ("old@example.com", "new@example.com"):
            await api.client.post("/api/v1/auth/password/forgot", json={"destination": address})
        await age(
            db_engine,
            "otp_challenges",
            "created_at",
            timedelta(hours=25),
            "destination = 'old@example.com'",
        )

        removed = await run(api)

        assert removed["one_time_codes"] == 1
        assert await count(db_engine, "otp_challenges", "destination = 'new@example.com'") == 1


async def test_a_live_login_keeps_its_start_while_its_old_tokens_go(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        for _ in range(3):
            assert (await api.client.post(REFRESH)).status_code == 200
        began = (await api.client.get("/api/v1/auth/sessions", headers=shopper.auth)).json()
        # Эхний гурван token удаан хугацааны өмнө дууссан; дөрөв дэх нь амьд.
        await execute(
            db_engine,
            "UPDATE refresh_tokens SET expires_at = now() - interval '40 days' "
            "WHERE used_at IS NOT NULL",
        )

        removed = await run(api)

        sessions = (await api.client.get("/api/v1/auth/sessions", headers=shopper.auth)).json()
        assert removed["refresh_tokens"] == 2  # эхний мөр үлдэнэ
        assert [s["created_at"] for s in sessions] == [s["created_at"] for s in began]
        assert (await api.client.post(REFRESH)).status_code == 200


async def test_a_login_that_ended_long_ago_goes_entirely(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)
        await api.client.post(REFRESH)
        await execute(
            db_engine, "UPDATE refresh_tokens SET expires_at = now() - interval '31 days'"
        )

        removed = await run(api)

        assert removed["refresh_tokens"] == 2
        assert await count(db_engine, "refresh_tokens") == 0


async def test_a_recently_expired_token_is_still_kept(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)
        await execute(
            db_engine, "UPDATE refresh_tokens SET expires_at = now() - interval '29 days'"
        )

        assert (await run(api))["refresh_tokens"] == 0


async def test_security_activity_is_kept_for_half_a_year_and_remembers_devices_that_long(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        await login(api, shopper.email, agent=SAFARI_IPHONE)
        await execute(db_engine, "DELETE FROM refresh_tokens")

        # Token нь цэвэрлэгдсэн ч iPhone танил хэвээр: дахин мэдэгдэхгүй.
        again = await login(api, shopper.email, agent=SAFARI_IPHONE)
        token = {"Authorization": f"Bearer {again.json()['access_token']}"}
        events = (await api.client.get("/api/v1/auth/security-events", headers=token)).json()
        assert [e["type"] for e in events].count("new_device") == 1

        await age(db_engine, "security_events", "created_at", timedelta(days=181), "true")
        assert (await run(api))["security_events"] == len(events)
        assert await count(db_engine, "security_events") == 0


async def test_a_failed_attempt_does_not_make_a_device_familiar(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        await login(api, shopper.email, "not the password", agent=CHROME_MAC)

        response = await login(api, shopper.email, agent=CHROME_MAC)
        token = {"Authorization": f"Bearer {response.json()['access_token']}"}
        events = (await api.client.get("/api/v1/auth/security-events", headers=token)).json()

    assert "new_device" in [e["type"] for e in events]


async def test_finished_emails_are_dropped_and_waiting_ones_are_never(
    api_factory: ApiFactory, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(housekeeping, "BATCH", 2)  # багцаар устгах нь бүгдийг барих ёстой
    async with api_factory(seed_count=0) as api:
        for status, days, how_many in (
            ("sent", 8, 5),
            ("sent", 6, 1),
            ("failed", 31, 1),
            ("failed", 8, 1),
            ("pending", 90, 1),
        ):
            for _ in range(how_many):
                await execute(
                    db_engine,
                    "INSERT INTO email_outbox (to_address, subject, status, updated_at) VALUES "
                    "('a@example.com', 's', :status, now() - make_interval(days => :days))",
                    status=status,
                    days=days,
                )

        removed = await run(api)

        assert (removed["sent_emails"], removed["failed_emails"]) == (5, 1)
        assert await count(db_engine, "email_outbox", "status = 'sent'") == 1
        assert await count(db_engine, "email_outbox", "status = 'failed'") == 1
        assert await count(db_engine, "email_outbox", "status = 'pending'") == 1
