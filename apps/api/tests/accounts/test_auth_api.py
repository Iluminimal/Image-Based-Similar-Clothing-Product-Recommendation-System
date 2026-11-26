import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import Response
from sqlalchemy import text

from angel.core.security import create_access_token
from tests.conftest import Api, ApiFactory
from tests.support.commerce import PASSWORD, another_client, register, unique_email

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


def without_request_id(response: Response) -> dict[str, object]:
    return {k: v for k, v in response.json().items() if k != "request_id"}


async def test_register_signs_the_user_in(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        response = await api.client.post(
            REGISTER,
            json={"email": " Ada@Example.COM ", "password": PASSWORD, "full_name": " Ada "},
        )

        body = response.json()
        assert response.status_code == 201
        assert body["user"] == {
            "id": body["user"]["id"],
            "email": "ada@example.com",
            "phone": None,
            "email_verified": False,
            "phone_verified": False,
            "full_name": "Ada",
            "role": "customer",
            "avatar_url": None,
            "has_password": True,
            "providers": [],
        }
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == api.settings.access_token_ttl_seconds
        # Нууц үг ч, hash ч буцахгүй (`has_password` нь зөвхөн тэмдэг).
        assert PASSWORD not in response.text
        assert "password_hash" not in response.text
        me = await api.client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == "ada@example.com"
        assert response.headers["cache-control"] == "no-store"


async def test_refresh_token_is_an_httponly_scoped_cookie_never_in_the_body(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        response = await api.client.post(
            REGISTER, json={"email": unique_email(), "password": PASSWORD, "full_name": "Ada"}
        )

        cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
        refresh = cookies["lk_refresh"].lower()
        assert "httponly" in refresh
        assert "samesite=lax" in refresh
        assert "path=/api/v1/auth" in refresh
        assert "max-age=" in refresh
        assert "httponly" not in cookies["lk_session"].lower()  # edge proxy уншиж чадна
        assert "refresh" not in response.json()
        assert "secure" not in refresh  # тестэд http; prod дээр secure заавал (config тестийг үз)


async def test_register_rejects_duplicates_weak_passwords_and_bad_emails(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        email = unique_email()
        await register(api.client, email)

        duplicate = await api.client.post(
            REGISTER, json={"email": email.upper(), "password": PASSWORD, "full_name": "Eve"}
        )
        short = await api.client.post(
            REGISTER, json={"email": unique_email(), "password": "short", "full_name": "Eve"}
        )
        bad_email = await api.client.post(
            REGISTER, json={"email": "not-an-email", "password": PASSWORD, "full_name": "Eve"}
        )
        extra = await api.client.post(
            REGISTER,
            json={
                "email": unique_email(),
                "password": PASSWORD,
                "full_name": "E",
                "is_admin": True,
            },
        )

        assert duplicate.status_code == 409
        assert duplicate.json()["type"] == "urn:angel:problem:email-taken"
        assert short.status_code == bad_email.status_code == extra.status_code == 422


async def test_passwords_are_stored_as_argon2_hashes(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)

        async with api.app.state.engine.connect() as connection:
            stored = (
                await connection.execute(
                    text("SELECT password_hash FROM users WHERE id = :id"), {"id": shopper.user_id}
                )
            ).scalar_one()
        assert stored.startswith("$argon2id$")
        assert PASSWORD not in stored


async def test_login_succeeds_and_fails_with_the_same_error_for_unknown_and_wrong(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        email = unique_email()
        await register(api.client, email)
        async with another_client(api) as browser:
            ok = await browser.post(LOGIN, json={"email": email.upper(), "password": PASSWORD})
            wrong = await browser.post(LOGIN, json={"email": email, "password": "wrong-password!"})
            unknown = await browser.post(
                LOGIN, json={"email": unique_email(), "password": PASSWORD}
            )

        assert ok.status_code == 200
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["type"] == "urn:angel:problem:invalid-credentials"
        # "Ийм хэрэглэгч байхгүй" ба "нууц үг буруу" хоёрын request id ч ялгаагүй.
        assert without_request_id(wrong) == without_request_id(unknown)


async def test_failed_logins_for_one_email_are_limited_and_success_resets_the_count(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0, rate_limit_login_email="3/300") as api:
        email = unique_email()
        await register(api.client, email)
        async with another_client(api) as browser:
            for _ in range(3):
                response = await browser.post(
                    LOGIN, json={"email": email, "password": "nope-nope-nope"}
                )
                assert response.status_code == 401
            locked = await browser.post(LOGIN, json={"email": email, "password": PASSWORD})

        assert locked.status_code == 429
        assert locked.headers["retry-after"]
        assert locked.json()["type"] == "urn:angel:problem:rate-limited"

    async with api_factory(seed_count=0, rate_limit_login_email="3/300") as api:
        email = unique_email()
        await register(api.client, email)
        async with another_client(api) as browser:
            for _ in range(2):
                await browser.post(LOGIN, json={"email": email, "password": "nope-nope-nope"})
            assert (
                await browser.post(LOGIN, json={"email": email, "password": PASSWORD})
            ).status_code == 200
            for _ in range(2):  # тоолуур дахин 0-ээс эхэлсэн
                assert (
                    await browser.post(LOGIN, json={"email": email, "password": "nope-nope-nope"})
                ).status_code == 401


async def test_login_is_rate_limited_per_address(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0, rate_limit_login="2/60") as api:
        codes = [
            (
                await api.client.post(LOGIN, json={"email": unique_email(), "password": PASSWORD})
            ).status_code
            for _ in range(3)
        ]

        assert codes == [401, 401, 429]


async def test_refresh_rotates_the_token_and_returns_a_working_access_token(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        first_cookie = api.client.cookies.get("lk_refresh")

        refreshed = await api.client.post(REFRESH)

        assert refreshed.status_code == 200
        assert api.client.cookies.get("lk_refresh") != first_cookie
        me = await api.client.get(
            ME, headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}
        )
        assert me.json()["id"] == shopper.user_id


async def test_replaying_a_used_refresh_token_revokes_the_whole_session(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)
        stolen = api.client.cookies.get("lk_refresh")
        await api.client.post(REFRESH)  # зөв ротаци
        assert stolen is not None
        # Хугацааны зөвшөөрлөөс хойш давтан ашигласан token бол хулгай, давхар дарсан биш.
        async with api.app.state.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE refresh_tokens SET used_at = now() - interval '1 hour' "
                    "WHERE used_at IS NOT NULL"
                )
            )

        async with another_client(api, refresh_token=stolen) as thief:
            replay = await thief.post(REFRESH)
        rotated = await api.client.post(REFRESH)  # хохирогчийн сүүлийн token ч идэвхгүй

        assert replay.status_code == 401
        assert rotated.status_code == 401
        async with api.app.state.engine.connect() as connection:
            live = (
                await connection.execute(
                    text("SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL")
                )
            ).scalar_one()
        assert live == 0


async def age_used_tokens(api: Api, by: timedelta = timedelta(hours=1)) -> None:
    """Зөвшөөрлийн цонх өнгөрсөн мэт болгоно (дараалал хадгалагдана)."""
    async with api.app.state.engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE refresh_tokens SET used_at = used_at - cast(:by AS interval) "
                "WHERE used_at IS NOT NULL"
            ),
            {"by": by},
        )


async def refresh_with(api: Api, token: str) -> tuple[int, str | None]:
    """`token` cookie-тэй browser-ийн нэг refresh: (status, хариугаар ирсэн шинэ token)."""
    async with another_client(api, refresh_token=token) as browser:
        response = await browser.post(REFRESH)
        return response.status_code, response.cookies.get("lk_refresh")


async def signed_in_token(api: Api) -> str:
    await register(api.client)
    token = api.client.cookies.get("lk_refresh")
    assert token is not None
    return token


async def test_a_refresh_whose_answer_never_arrived_does_not_sign_the_person_out(
    api_factory: ApiFactory,
) -> None:
    """Хуудас шилжих, сүлжээ тасрах үед сервер token-ийг сольсон ч browser шинийг аваагүй байдаг."""
    async with api_factory(seed_count=0) as api:
        first = await signed_in_token(api)
        await refresh_with(api, first)  # хариу алдагдсан: browser-т хуучин token үлдсэн

        status, current = await refresh_with(api, first)

        assert status == 200
        assert current is not None
        assert (await refresh_with(api, current))[0] == 200


async def test_two_tabs_may_refresh_at_once_and_only_one_chain_stays_alive(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        first = await signed_in_token(api)

        (status_a, tab_a), (status_b, tab_b) = (
            await refresh_with(api, first),
            await refresh_with(api, first),
        )
        assert (status_a, status_b) == (200, 200)
        assert tab_a is not None
        assert tab_b is not None
        # Cookie нь нэг: аль нь үлдсэн ч ажиллана, нөгөө нь үхнэ.
        status, newest = await refresh_with(api, tab_a)
        assert status == 200
        assert newest is not None
        assert (await refresh_with(api, tab_b))[0] == 401
        assert (await refresh_with(api, newest))[0] == 200


async def test_an_older_token_is_refused_once_the_login_has_moved_on(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        first = await signed_in_token(api)
        _, second = await refresh_with(api, first)
        assert second is not None
        _, third = await refresh_with(api, second)
        assert third is not None

        status, _ = await refresh_with(api, first)

        assert status == 401  # цонхны дотор ч гэсэн
        assert (await refresh_with(api, third))[0] == 200  # хулгай гэж үзэхгүй


async def test_a_token_that_lost_the_race_is_theft_after_the_window(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        first = await signed_in_token(api)
        _, kept = await refresh_with(api, first)
        _, spare = await refresh_with(api, first)
        assert kept is not None
        assert spare is not None
        _, newest = await refresh_with(api, kept)
        assert newest is not None
        await age_used_tokens(api)

        assert (await refresh_with(api, spare))[0] == 401
        assert (await refresh_with(api, newest))[0] == 401  # нэвтрэлт бүхэлдээ дууссан


async def test_after_signing_out_no_old_token_comes_back_to_life(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        first = await signed_in_token(api)
        refreshed = await api.client.post(REFRESH)
        assert refreshed.status_code == 200
        assert (await api.client.post(LOGOUT)).status_code == 204

        assert (await refresh_with(api, first))[0] == 401


async def test_signing_out_while_another_tab_refreshes_leaves_no_live_token(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        for _ in range(8):
            first = await signed_in_token(api)
            _, second = await refresh_with(api, first)
            assert second is not None

            async with another_client(api, refresh_token=first) as old_tab:
                await asyncio.gather(refresh_with(api, second), old_tab.post(LOGOUT))

        async with api.app.state.engine.connect() as connection:
            live = (
                await connection.execute(
                    text("SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL")
                )
            ).scalar_one()
        assert live == 0


async def test_the_device_list_shows_one_login_once(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        first = api.client.cookies.get("lk_refresh")
        assert first is not None
        await refresh_with(api, first)
        await refresh_with(api, first)  # нэг нэвтрэлтэд хоёр ашиглагдаагүй token

        sessions = await api.client.get("/api/v1/auth/sessions", headers=shopper.auth)

        assert sessions.status_code == 200, sessions.text
        assert len(sessions.json()) == 1


async def test_concurrent_refreshes_with_one_token_leave_one_usable_login(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        token = await signed_in_token(api)

        results = await asyncio.gather(*(refresh_with(api, token) for _ in range(4)))

        assert [status for status, _ in results] == [200, 200, 200, 200]
        issued = [new for _, new in results if new is not None]
        assert len(set(issued)) == 4
        assert (await refresh_with(api, issued[0]))[0] == 200
        assert [(await refresh_with(api, other))[0] for other in issued[1:]] == [401] * 3


async def test_expired_refresh_token_is_rejected(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)
        async with api.app.state.engine.begin() as connection:
            await connection.execute(
                text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'")
            )

        assert (await api.client.post(REFRESH)).status_code == 401


async def test_refresh_without_a_cookie_is_401(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        response = await api.client.post(REFRESH)

        assert response.status_code == 401
        assert response.json()["type"] == "urn:angel:problem:unauthenticated"


async def test_logout_ends_the_session_and_clears_cookies(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)
        token = api.client.cookies.get("lk_refresh")
        assert token is not None

        response = await api.client.post(LOGOUT)

        assert response.status_code == 204
        cleared = " ".join(response.headers.get_list("set-cookie")).lower()
        assert "lk_refresh=" in cleared
        assert "max-age=0" in cleared
        async with another_client(api, refresh_token=token) as browser:
            assert (await browser.post(REFRESH)).status_code == 401
        assert (await api.client.post(LOGOUT)).status_code == 204  # давтан дуудахад ч хэвээр


async def test_protected_endpoints_need_a_valid_unexpired_token(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        expired = create_access_token(
            shopper.user_id,
            api.settings.jwt_secret,
            60,
            now=datetime.now(UTC) - timedelta(hours=1),
        ).value

        missing = await api.client.get(ME)
        garbage = await api.client.get(ME, headers={"Authorization": "Bearer nonsense"})
        old = await api.client.get(ME, headers={"Authorization": f"Bearer {expired}"})
        orders = await api.client.get("/api/v1/orders")

        assert [r.status_code for r in (missing, garbage, old, orders)] == [401, 401, 401, 401]
        assert missing.headers["www-authenticate"] == "Bearer"
        assert missing.json()["type"] == "urn:angel:problem:unauthenticated"


async def test_cookie_endpoints_refuse_cross_site_requests(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        await register(api.client)

        evil = await api.client.post(REFRESH, headers={"Origin": "https://evil.example"})
        fetch_metadata = await api.client.post(REFRESH, headers={"Sec-Fetch-Site": "cross-site"})
        ours = await api.client.post(REFRESH, headers={"Origin": "http://localhost:3000"})

        assert evil.status_code == 403
        assert evil.json()["type"] == "urn:angel:problem:forbidden-origin"
        assert fetch_metadata.status_code == 403
        assert ours.status_code == 200


async def test_responses_carry_security_headers(api_factory: ApiFactory) -> None:
    async with api_factory(seed_count=0) as api:
        response = await api.client.get("/healthz")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
