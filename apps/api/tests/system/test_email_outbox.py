"""Мэдэгдлийн имэйл алдагдахгүй: өөрчлөлттэй хамт хадгалж, SMTP унавал дахин оролдоно."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from angel.cli.outbox import describe_outbox, retry_failed
from angel.core.mail import Email, MailDeliveryError
from angel.services.system import outbox
from angel.services.system.outbox import MAX_ATTEMPTS, RETRY_DELAYS, queue_email
from tests.admin.test_admin_orders_api import in_stock, place_order
from tests.conftest import Api, ApiFactory
from tests.support.commerce import register
from tests.support.fakes import RecordingGateway, RecordingMailer
from tests.support.mail import deliver_mail

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]


class DownMailer:
    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, email: Email) -> None:
        self.attempts += 1
        raise MailDeliveryError("SMTPConnectError")


@pytest.fixture
async def api(api_factory: ApiFactory, tmp_path: Path) -> AsyncIterator[Api]:
    async with api_factory(seed_count=0, media_dir=tmp_path) as running:
        yield running


async def rows(engine: AsyncEngine) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT status, attempts, last_error, body, sent_at, "
                "next_attempt_at - now() AS wait FROM email_outbox ORDER BY id"
            )
        )
        return [dict(row._mapping) for row in result.all()]


async def make_due(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE email_outbox SET next_attempt_at = now()"))


async def queue(api: Api, to: str = "buyer@example.com", subject: str = "Сайн уу") -> None:
    async with api.app.state.sessions() as session, session.begin():
        queue_email(session, Email(to=to, subject=subject, body="Нууц агуулга"))


async def test_a_queued_email_is_sent_once_and_its_text_is_then_forgotten(
    api: Api, db_engine: AsyncEngine
) -> None:
    mailer = RecordingMailer()
    await queue(api)

    assert await deliver_mail(api, mailer) == 1
    assert await deliver_mail(api, mailer) == 0

    [email] = mailer.sent
    assert (email.to, email.subject, email.body) == ("buyer@example.com", "Сайн уу", "Нууц агуулга")
    [row] = await rows(db_engine)
    assert (row["status"], row["attempts"], row["body"]) == ("sent", 1, None)
    assert row["sent_at"] is not None


async def test_an_email_that_could_not_be_sent_waits_and_goes_out_later(
    api: Api, db_engine: AsyncEngine
) -> None:
    await queue(api)
    down, up = DownMailer(), RecordingMailer()

    await deliver_mail(api, down)
    await deliver_mail(api, down)  # цаг нь болоогүй тул дахин оролдохгүй

    [row] = await rows(db_engine)
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "SMTPConnectError")
    assert row["body"] == "Нууц агуулга"
    assert down.attempts == 1
    assert RETRY_DELAYS[0] - timedelta(seconds=10) < row["wait"] <= RETRY_DELAYS[0]

    await make_due(db_engine)
    assert await deliver_mail(api, up) == 1
    [row] = await rows(db_engine)
    assert (row["status"], row["attempts"], row["last_error"]) == ("sent", 2, None)


async def test_each_failure_waits_longer_and_the_last_one_gives_up(
    api: Api, db_engine: AsyncEngine
) -> None:
    await queue(api)
    down = DownMailer()
    waits = []

    for _ in range(MAX_ATTEMPTS):
        await make_due(db_engine)
        await deliver_mail(api, down)
        waits.append((await rows(db_engine))[0]["wait"])

    [row] = await rows(db_engine)
    assert (row["status"], row["attempts"]) == ("failed", MAX_ATTEMPTS)
    for wait, planned in zip(waits, RETRY_DELAYS, strict=False):
        assert planned - timedelta(seconds=30) < wait <= planned
    await make_due(db_engine)
    await deliver_mail(api, down)
    assert down.attempts == MAX_ATTEMPTS  # орхисныг дахин оролдохгүй


async def test_one_bad_email_does_not_hold_back_the_others(api: Api) -> None:
    class Picky(RecordingMailer):
        async def send(self, email: Email) -> None:
            if email.to == "bad@example.com":
                raise RuntimeError("unexpected")
            await super().send(email)

    mailer = Picky()
    for to in ("a@example.com", "bad@example.com", "b@example.com"):
        await queue(api, to)

    assert await deliver_mail(api, mailer) == 2
    assert [email.to for email in mailer.sent] == ["a@example.com", "b@example.com"]


async def test_a_send_that_hangs_is_cut_off_and_retried_later(
    api: Api, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Hangs:
        async def send(self, email: Email) -> None:
            await asyncio.sleep(30)  # хариу бүрийн хязгаарт багтаад хэзээ ч дуусахгүй сервер

    monkeypatch.setattr(outbox, "SEND_DEADLINE", timedelta(milliseconds=50))
    await queue(api)

    assert await asyncio.wait_for(deliver_mail(api, Hangs()), timeout=5) == 0

    [row] = await rows(db_engine)
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "TimeoutError")


def test_the_lease_outlasts_a_whole_batch_at_its_slowest() -> None:
    """Үгүй бол өөр worker хүлээж буй имэйлийг дахин авч, хоёр удаа илгээнэ."""
    assert outbox.BATCH * outbox.SEND_DEADLINE < outbox.LEASE


async def test_two_workers_never_send_the_same_email(api: Api) -> None:
    class Slow(RecordingMailer):
        async def send(self, email: Email) -> None:
            await asyncio.sleep(0.01)
            await super().send(email)

    mailer = Slow()
    for index in range(45):
        await queue(api, f"person{index}@example.com")

    sent = await asyncio.gather(deliver_mail(api, mailer), deliver_mail(api, mailer))

    assert sum(sent) == 45
    assert len({email.to for email in mailer.sent}) == len(mailer.sent) == 45


async def test_an_email_whose_worker_died_is_picked_up_again(
    api: Api, db_engine: AsyncEngine
) -> None:
    class Dies:
        async def send(self, email: Email) -> None:
            raise asyncio.CancelledError  # процесс зогссон мэт: үр дүн бичигдэхгүй

    await queue(api)
    with pytest.raises(asyncio.CancelledError):
        await deliver_mail(api, Dies())
    mailer = RecordingMailer()
    assert await deliver_mail(api, mailer) == 0  # эзэмшлийн хугацаа дуусаагүй

    await make_due(db_engine)

    assert await deliver_mail(api, mailer) == 1


async def test_an_email_is_part_of_the_change_that_caused_it(
    api: Api, db_engine: AsyncEngine
) -> None:
    async def change_that_fails() -> None:
        async with api.app.state.sessions() as session, session.begin():
            queue_email(session, Email(to="a@example.com", subject="x", body="y"))
            await session.flush()
            raise RuntimeError("the change failed")

    with pytest.raises(RuntimeError):
        await change_that_fails()

    assert await rows(db_engine) == []


async def test_an_order_email_survives_an_unreachable_mail_server(
    api_factory: ApiFactory, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    async with api_factory(media_dir=tmp_path, gateway=RecordingGateway()) as api:
        api.app.state.mailer = down = DownMailer()

        shopper, number = await place_order(api, in_stock(api, 0), pay=True)
        # Хүсэлт SMTP-г хүлээхгүй: төлбөр амжилттай, имэйл дараалалд үлдсэн.
        assert down.attempts == 0
        await deliver_mail(api)
        assert down.attempts >= 1

        await make_due(db_engine)
        up = RecordingMailer()
        await deliver_mail(api, up)

    confirmations = [m for m in up.sent if number in m.subject]
    assert [m.to for m in confirmations] == [shopper.email]


async def test_a_one_time_code_is_sent_at_once_and_never_stored(
    api: Api, db_engine: AsyncEngine
) -> None:
    api.app.state.mailer = mailer = RecordingMailer()

    response = await api.client.post(
        "/api/v1/auth/otp/request", json={"destination": "new@example.com"}
    )

    assert response.status_code == 202
    assert mailer.last_code()  # worker ажиллуулаагүй ч очсон
    assert await rows(db_engine) == []


async def test_a_one_time_code_that_cannot_be_sent_is_reported(api: Api) -> None:
    api.app.state.mailer = DownMailer()

    response = await api.client.post(
        "/api/v1/auth/otp/request", json={"destination": "new@example.com"}
    )

    assert response.status_code == 503
    assert response.json()["type"] == "urn:angel:problem:email-unavailable"


async def test_the_operator_sees_failed_emails_without_their_text_and_can_retry_them(
    api: Api, db_engine: AsyncEngine
) -> None:
    await register(api.client, "operator-view@example.com")
    await queue(api, "someone.private@example.com", "Захиалга LK-1")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE email_outbox SET status = 'failed', last_error = 'SMTPConnectError'")
        )

    report = await describe_outbox(db_engine)
    retried = await retry_failed(db_engine)

    assert "failed: 2" in report
    assert "SMTPConnectError" in report
    assert "Захиалга LK-1" in report
    assert "s***@example.com" in report
    assert "someone.private" not in report
    assert "Нууц агуулга" not in report
    assert retried == "2 emails queued again"
    mailer = RecordingMailer()
    assert await deliver_mail(api, mailer) == 2
