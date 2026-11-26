"""Мэдэгдлийн имэйл outbox-оор явдаг. Тестэд дэвсгэрийн worker ажиллахгүй тул тест өөрөө нэг удаа
ажиллуулна."""

from angel.core.mail import Mailer
from angel.services.system.outbox import OutboxDispatcher
from tests.conftest import Api


async def deliver_mail(api: Api, mailer: Mailer | None = None) -> int:
    """Цаг нь болсон бүх имэйлийг апп-ын (эсвэл өгсөн) mailer-ээр илгээж, тоог нь буцаана."""
    return await OutboxDispatcher(api.app.state.sessions, mailer or api.app.state.mailer).run_once()
