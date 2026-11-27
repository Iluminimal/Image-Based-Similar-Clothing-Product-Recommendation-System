"""мэдэгдлийн имэйлийн outbox, устгасан бүртгэлийн үлдэгдэл

Revision ID: e4b8f2a6c173
Revises: d7a1c4e9b258
Create Date: 2026-12-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b8f2a6c173"
down_revision: str | Sequence[str] | None = "d7a1c4e9b258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Өмнө нь устгасан (нэргүйжүүлсэн) бүртгэлүүд.
_DELETED = (
    "SELECT id FROM users WHERE email LIKE 'deleted-%@deleted.invalid' AND is_active IS FALSE"
)


def upgrade() -> None:
    """Schema-г шинэчилж, өмнө нь устгасан бүртгэлийн үлдсэн хувийн мэдээллийг арилгана."""
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("to_address", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name=op.f("ck_email_outbox_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        "ix_email_outbox_due",
        "email_outbox",
        ["next_attempt_at", "id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_email_outbox_to_address", "email_outbox", ["to_address"])

    # Эдгээр account-ын хаяг аль хэдийн солигдсон тул энд зөвхөн id-аар нь олдох өгөгдлийг арилгана.
    # Хуучин хаягаар үлдсэн нэг удаагийн кодыг цэвэрлэгч нэг хоногийн дараа устгана.
    # S608: `_DELETED` бол энэ файлын тогтмол, хэрэглэгчийн оролт биш.
    for statement in (
        f"DELETE FROM security_events WHERE user_id IN ({_DELETED})",  # noqa: S608
        f"DELETE FROM otp_challenges WHERE user_id IN ({_DELETED})",  # noqa: S608
        "UPDATE order_requests SET details = NULL WHERE order_id IN "  # noqa: S608
        f"(SELECT id FROM orders WHERE user_id IN ({_DELETED}))",
    ):
        op.execute(sa.text(statement))


def downgrade() -> None:
    """Schema-г буцаана. Илгээгдээгүй имэйл байвал алдахгүйн тулд зогсоно (арилгасан хувийн
    мэдээлэл буцаж ирэхгүй)."""
    waiting = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM email_outbox WHERE status = 'pending'"))
        .scalar_one()
    )
    if waiting:
        raise RuntimeError(f"{waiting} emails are still waiting to be sent")
    op.drop_table("email_outbox")
