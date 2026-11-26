"""Хуучин refresh token цэвэрлэгдсэн ч "шинэ төхөөрөмжөөс нэвтэрлээ" мэдэгдэл алдагдахгүй."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.accounts.test_security_events_api import SAFARI_IPHONE, login
from tests.conftest import ApiFactory
from tests.support.commerce import register

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]


async def test_a_long_unused_account_still_hears_about_a_new_device(
    api_factory: ApiFactory, db_engine: AsyncEngine
) -> None:
    async with api_factory(seed_count=0) as api:
        owner = await register(api.client)
        async with db_engine.begin() as connection:
            # Цэвэрлэгчийн хийх зүйл: удаан ашиглаагүй бүртгэлийн бүх token устсан.
            await connection.execute(text("DELETE FROM refresh_tokens"))

        response = await login(api, owner.email, agent=SAFARI_IPHONE)
        assert response.status_code == 200, response.text
        events = await api.client.get(
            "/api/v1/auth/security-events",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )

    assert "new_device" in [item["type"] for item in events.json()]
