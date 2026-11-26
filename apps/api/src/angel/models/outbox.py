"""Илгээх имэйлийн дараалал (outbox)-ын хүснэгт. Ажиллах зарчим: `services/system/outbox.py`."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from angel.db.base import Base
from angel.models.mixins import TimestampMixin


class OutboxEmail(TimestampMixin, Base):
    """Илгээх ёстой мэдэгдлийн имэйл. Өөрчлөлттэй (захиалга, нууц үг...) нэг transaction-д бичигддэг
    тул өөрчлөлт буцвал имэйл ч үүсэхгүй, commit хийгдвэл хэзээ ч мартагдахгүй. Нэг удаагийн код
    энд хэзээ ч орохгүй. Илгээмэгц агуулгыг нь арилгана."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="status_valid"),
        # Worker зөвхөн хүлээж буйг хайна.
        Index(
            "ix_email_outbox_due",
            "next_attempt_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        # Бүртгэл устгахад тухайн хаягийн дууссан мөрүүдийг олно.
        Index("ix_email_outbox_to_address", "to_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    # Worker энэ цагаас өмнө авахгүй: дахин оролдох хуваарь, мөн илгээж буй worker-ийн түр эзэмшил.
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Зөвхөн алдааны төрөл: серверийн хариу хаяг агуулж болно.
    last_error: Mapped[str | None] = mapped_column(String(100))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
