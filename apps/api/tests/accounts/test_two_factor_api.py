"""Ажилтны хоёр шатлалт нэвтрэлт: тохируулах, түүнтэй нэвтрэх, шаардах, арилгах."""

import time

import pytest
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from angel.core.totp import code_at
from angel.services.admin.users import reset_two_factor
from tests.accounts.test_staff_security_api import make_staff
from tests.conftest import Api, ApiFactory
from tests.support.commerce import PASSWORD, register

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

LOGIN = "/api/v1/auth/login"
STATUS = "/api/v1/auth/2fa"
SETUP = "/api/v1/auth/2fa/setup"
ENABLE = "/api/v1/auth/2fa/enable"
ADMIN_ORDERS = "/api/v1/admin/orders"


def totp(secret: str, offset: int = 0) -> str:
    return code_at(secret, int(time.time() // 30) + offset)


async def login(api: Api, email: str, code: str | None = None) -> Response:
    body = {"email": email, "password": PASSWORD, **({"totp_code": code} if code else {})}
    return await api.client.post(LOGIN, json=body)


def bearer(response: Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def enrol(api: Api, email: str) -> tuple[str, list[str], dict[str, str]]:
    headers = bearer(await login(api, email))
    setup = await api.client.post(SETUP, json={"password": PASSWORD}, headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["qr_image"].startswith("data:image/svg+xml")
    # Өмнөх алхмын кодоор идэвхжүүлнэ: дараагийн нэвтрэлт одоогийн кодыг ашиглах боломжтой.
    enabled = await api.client.post(ENABLE, json={"code": totp(secret, -1)}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    return secret, enabled.json()["codes"], headers


async def test_after_enrolment_the_password_alone_is_not_enough(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        email = await make_staff(db_engine, "admin")
        secret, codes, _ = await enrol(api, email)

        without = await login(api, email)
        wrong = await login(api, email, "000000" if totp(secret) != "000000" else "111111")
        current = totp(secret)
        right = await login(api, email, current)
        replayed = await login(api, email, current)

        assert len(codes) == 10
        assert (without.status_code, without.json()["type"]) == (
            401,
            "urn:angel:problem:totp-required",
        )
        assert wrong.json()["type"] == "urn:angel:problem:totp-invalid"
        assert "lk_refresh" not in wrong.headers.get("set-cookie", "")
        assert right.status_code == 200, right.text
        assert replayed.status_code == 401
        async with db_engine.connect() as connection:
            stored = (
                await connection.execute(
                    text("SELECT totp_secret FROM users WHERE email = :e"), {"e": email}
                )
            ).scalar_one()
        assert secret not in stored


async def test_a_recovery_code_works_exactly_once(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        email = await make_staff(db_engine, "warehouse")
        _, codes, headers = await enrol(api, email)

        first = await login(api, email, codes[0])
        second = await login(api, email, codes[0])
        left = (await api.client.get(STATUS, headers=headers)).json()

        assert first.status_code == 200, first.text
        assert second.status_code == 401
        assert left == {"enabled": True, "required": False, "recovery_codes_left": 9}


async def test_when_required_the_back_office_is_closed_until_enrolment(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0, staff_2fa_required=True) as api:
        email = await make_staff(db_engine, "admin")
        headers = bearer(await login(api, email))

        before = await api.client.get(ADMIN_ORDERS, headers=headers)
        _, _, headers = await enrol(api, email)
        after = await api.client.get(ADMIN_ORDERS, headers=headers)

        assert (before.status_code, before.json()["type"]) == (
            403,
            "urn:angel:problem:totp-setup-required",
        )
        assert after.status_code == 200, after.text


async def test_it_cannot_be_set_up_again_or_by_a_customer_or_with_a_wrong_password(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        email = await make_staff(db_engine, "admin")
        headers = bearer(await login(api, email))
        wrong = await api.client.post(SETUP, json={"password": "not-the-password"}, headers=headers)
        _, _, headers = await enrol(api, email)
        again = await api.client.post(SETUP, json={"password": PASSWORD}, headers=headers)
        shopper = await register(api.client)
        customer = await api.client.post(SETUP, json={"password": PASSWORD}, headers=shopper.auth)

        assert (wrong.status_code, again.status_code, customer.status_code) == (403, 409, 403)


async def test_without_a_configured_secret_it_refuses_instead_of_locking_staff_out(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0, jwt_secret="") as api:
        email = await make_staff(db_engine, "admin")
        headers = bearer(await login(api, email))

        response = await api.client.post(SETUP, json={"password": PASSWORD}, headers=headers)

        assert (response.status_code, response.json()["type"]) == (
            503,
            "urn:angel:problem:totp-unavailable",
        )


async def test_the_server_command_clears_it_and_ends_every_login(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        email = await make_staff(db_engine, "admin")
        await enrol(api, email)

        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            assert await reset_two_factor(session, email=email) is not None

        assert (await api.client.post("/api/v1/auth/refresh")).status_code == 401
        assert (await login(api, email)).status_code == 200


async def test_a_staff_member_with_two_factor_resets_the_password_but_must_still_sign_in(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0, otp_dev_code="000000") as api:
        email = await make_staff(db_engine, "admin")
        secret, _, _ = await enrol(api, email)
        api.client.cookies.clear()

        await api.client.post("/api/v1/auth/password/forgot", json={"destination": email})
        reset = await api.client.post(
            "/api/v1/auth/password/reset",
            json={
                "destination": email,
                "code": "000000",
                "new_password": "another-long-passphrase",
            },
        )
        with_both = await api.client.post(
            LOGIN,
            json={
                "email": email,
                "password": "another-long-passphrase",
                "totp_code": totp(secret),
            },
        )

        assert (reset.status_code, reset.json()["type"]) == (
            403,
            "urn:angel:problem:sign-in-required",
        )
        assert "lk_refresh" not in reset.headers.get("set-cookie", "")
        assert with_both.status_code == 200, with_both.text


async def test_resetting_the_password_does_not_give_fresh_guesses_at_the_second_factor(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(
        seed_count=0,
        otp_dev_code="000000",
        rate_limit_enabled=True,
        rate_limit_login_email_daily="3/86400",
    ) as api:
        email = await make_staff(db_engine, "admin")
        secret, _, _ = await enrol(api, email)
        wrong = "000000" if totp(secret) != "000000" else "111111"
        for _ in range(3):
            await login(api, email, wrong)

        await api.client.post("/api/v1/auth/password/forgot", json={"destination": email})
        await api.client.post(
            "/api/v1/auth/password/reset",
            json={
                "destination": email,
                "code": "000000",
                "new_password": "another-long-passphrase",
            },
        )
        after = await api.client.post(
            LOGIN,
            json={"email": email, "password": "another-long-passphrase", "totp_code": totp(secret)},
        )

        assert after.status_code == 429, after.text
