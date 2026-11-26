"""Ажилтны бүртгэл болон эмзэг үйлдлийн хамгаалалт: ажилтан зөвхөн нууц үгээр нэвтэрнэ, нууц үггүй
бүртгэл эмзэг өөрчлөлтийн өмнө шинэ кодоор өөрийгөө дахин батална, дуусаагүй захиалгатай бүртгэл
устахгүй."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from angel.services.admin.users import provision_staff
from tests.accounts.test_oauth_api import sign_in as sign_in_with_google
from tests.conftest import Api, ApiFactory
from tests.support.accounts import OTP_REQUEST, OTP_VERIFY, install_sms, sign_in_with_phone
from tests.support.commerce import (
    PASSWORD,
    add_address,
    add_to_cart,
    checkout,
    register,
    set_role,
    unique_email,
)
from tests.support.fakes import RecordingMailer
from tests.support.mail import deliver_mail

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

STAFF = ["admin", "warehouse"]
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
FIXED = "000000"


async def make_staff(engine: AsyncEngine, role: str) -> str:
    """CLI-тай яг адил замаар (`provision_staff`) ажилтан үүсгэнэ."""
    email = unique_email()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await provision_staff(session, email=email, password=PASSWORD, full_name="Staff", role=role)
    return email


async def password_login(api: Api, email: str) -> int:
    response = await api.client.post(LOGIN, json={"email": email, "password": PASSWORD})
    return response.status_code


# --- ажилтан зөвхөн нууц үгээр ---------------------------------------------------------------


@pytest.mark.parametrize("role", STAFF)
async def test_a_code_never_signs_staff_in_or_touches_their_password(
    api_factory: ApiFactory, db_engine: AsyncEngine, role: str
) -> None:
    async with api_factory(seed_count=0, otp_dev_code=FIXED) as api:
        email = await make_staff(db_engine, role)
        mailer = RecordingMailer()
        api.app.state.mailer = mailer

        requested = await api.client.post(OTP_REQUEST, json={"destination": email})
        verified = await api.client.post(OTP_VERIFY, json={"destination": email, "code": FIXED})

        assert requested.status_code == 202  # гаднаас бусадтай адил харагдана
        assert mailer.sent == []  # ажилтанд нэвтрэх код илгээхгүй
        assert verified.status_code == 400
        assert verified.json()["type"] == "urn:angel:problem:otp-invalid"
        assert await password_login(api, email) == 200


async def test_a_staff_password_cannot_be_reset_with_a_code_without_two_factor(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0, otp_dev_code=FIXED) as api:
        email = await make_staff(db_engine, "admin")

        await api.client.post("/api/v1/auth/password/forgot", json={"destination": email})
        reset = await api.client.post(
            "/api/v1/auth/password/reset",
            json={"destination": email, "code": FIXED, "new_password": "another-long-passphrase"},
        )

        assert reset.status_code == 400
        assert await password_login(api, email) == 200


@pytest.mark.parametrize("role", STAFF)
async def test_google_never_signs_staff_in_or_removes_their_password(
    api_factory: ApiFactory, db_engine: AsyncEngine, role: str
) -> None:
    async with api_factory(seed_count=0, oauth_mode="fake") as api:
        email = await make_staff(db_engine, role)

        done = await sign_in_with_google(api.client, email)

        assert "error=google_failed" in done.headers["location"]
        assert "lk_refresh=" not in done.headers.get("set-cookie", "")
        assert await password_login(api, email) == 200


async def test_provisioned_staff_have_a_verified_email(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        email = await make_staff(db_engine, "warehouse")

        response = await api.client.post(LOGIN, json={"email": email, "password": PASSWORD})

        assert response.json()["user"]["email_verified"] is True


@pytest.mark.parametrize("role", STAFF)
@pytest.mark.parametrize("path", ["/api/v1/wishlist", "/api/v1/addresses"])
async def test_staff_have_no_wishlist_or_address_book(
    api_factory: ApiFactory, db_engine: AsyncEngine, role: str, path: str
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        await set_role(db_engine, shopper.user_id, role)

        response = await api.client.get(path, headers=shopper.auth)

        assert response.status_code == 403


# --- нууц үггүй бүртгэл эмзэг үйлдлийн өмнө дахин батална -----------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/api/v1/auth/password", {"new_password": "a-brand-new-passphrase"}),
        ("POST", "/api/v1/auth/email/request", {"email": "thief@example.com"}),
        ("POST", "/api/v1/auth/phone/request", {"phone": "+14155550199"}),
        ("DELETE", "/api/v1/auth/me", {"confirm": "{phone}"}),
    ],
)
async def test_a_session_alone_cannot_change_a_passwordless_account(
    api_factory: ApiFactory, method: str, path: str, body: dict[str, str]
) -> None:
    async with api_factory(seed_count=0) as api:
        sms = install_sms(api)
        shopper = await sign_in_with_phone(api, sms)
        phone = (await api.client.get(ME, headers=shopper.auth)).json()["phone"]
        payload = {key: value.format(phone=phone) for key, value in body.items()}

        response = await api.client.request(method, path, json=payload, headers=shopper.auth)

        assert response.status_code == 403, response.text
        assert response.json()["type"] == "urn:angel:problem:reauth-required"


async def test_a_fresh_code_confirms_a_passwordless_account_once(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        sms = install_sms(api)
        shopper = await sign_in_with_phone(api, sms)

        sent = await api.client.post("/api/v1/auth/reauth/request", headers=shopper.auth)
        code = sms.last_code()
        changed = await api.client.put(
            "/api/v1/auth/password",
            json={"new_password": "a-brand-new-passphrase", "reauth_code": code},
            headers=shopper.auth,
        )

        assert sent.status_code == 202, sent.text
        assert changed.status_code == 200, changed.text
        assert changed.json()["user"]["has_password"] is True


async def test_removing_an_unverified_password_with_a_code_tells_the_owner(
    api_factory: ApiFactory,
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)
        mailer = RecordingMailer()
        api.app.state.mailer = mailer

        await api.client.post(OTP_REQUEST, json={"destination": shopper.email})
        verified = await api.client.post(
            OTP_VERIFY, json={"destination": shopper.email, "code": mailer.last_code()}
        )

        assert verified.status_code == 200, verified.text
        await deliver_mail(api)
        assert any("нууц үг" in m.subject and m.to == shopper.email for m in mailer.sent)


# --- дуусаагүй захиалга ----------------------------------------------------------------------


async def test_an_account_with_an_unfinished_order_cannot_be_deleted(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory() as api:
        shopper = await register(api.client)
        address = await add_address(shopper)
        product = api.entries[0].product_id
        await add_to_cart(api.client, product, token=shopper.token)
        placed = await checkout(shopper, address)
        assert placed.status_code == 200, placed.text
        number = placed.json()["order"]["number"]

        async def delete() -> tuple[int, str]:
            response = await api.client.request(
                "DELETE",
                ME,
                json={"confirm": shopper.email, "password": PASSWORD},
                headers=shopper.auth,
            )
            return response.status_code, response.text

        for status in ("pending", "paid", "shipped"):
            async with db_engine.begin() as connection:
                await connection.execute(
                    text("UPDATE orders SET status = :s WHERE number = :n"),
                    {"s": status, "n": number},
                )
            code, body = await delete()
            assert code == 409, (status, body)
            assert "urn:angel:problem:open-orders" in body

        async with db_engine.begin() as connection:
            await connection.execute(
                text("UPDATE orders SET status = 'delivered' WHERE number = :n"), {"n": number}
            )
        assert (await delete())[0] == 204


# --- ажилтан болгох command -------------------------------------------------------------------


async def test_a_passwordless_account_cannot_become_staff_without_getting_a_password(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        mailer = RecordingMailer()
        api.app.state.mailer = mailer
        email = unique_email()
        await api.client.post(OTP_REQUEST, json={"destination": email})
        await api.client.post(OTP_VERIFY, json={"destination": email, "code": mailer.last_code()})

        # Нууц үггүй ажилтан хаанаас ч нэвтэрч чадахгүй болох байсан.
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            with pytest.raises(ValueError, match="password"):
                await provision_staff(session, email=email, password=None, full_name="x")


async def test_becoming_staff_ends_the_logins_the_account_already_had(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        shopper = await register(api.client)

        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await provision_staff(session, email=shopper.email, password=None, full_name="x")

        # Урьд нь үүссэн session (өөр хүнийх ч байж болно) ажилтны эрх авахгүй.
        assert (await api.client.post("/api/v1/auth/refresh")).status_code == 401
