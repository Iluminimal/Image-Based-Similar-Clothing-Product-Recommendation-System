"""буцаах ёстой төлбөрийн төлөв, checkout хүсэлтийн hash

Revision ID: c5e2a8f4b913
Revises: b3c8d1f6a247
Create Date: 2026-11-30 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e2a8f4b913"
down_revision: str | Sequence[str] | None = "b3c8d1f6a247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "'requires_payment', 'succeeded', 'failed', 'canceled', 'refunded'"


def _statuses(values: str) -> None:
    op.drop_constraint(op.f("ck_payments_status_valid"), "payments")
    op.create_check_constraint(
        op.f("ck_payments_status_valid"), "payments", f"status IN ({values})"
    )


def upgrade() -> None:
    """Schema-г шинэчилнэ."""
    _statuses(f"{_OLD}, 'refund_pending'")
    # Sweep минут тутам буцаах ёстой төлбөрүүдийг хайна. Ийм мөр цөөн тул partial index ашиглана.
    op.create_index(
        "ix_payments_refund_pending",
        "payments",
        ["order_id"],
        postgresql_where=sa.text("status = 'refund_pending'"),
    )
    op.add_column("orders", sa.Column("request_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Schema-г буцаана. Буцааж өгөөгүй төлбөр байвал мэдээллийг нь алдахгүйн тулд зогсоно."""
    owed = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM payments WHERE status = 'refund_pending'"))
        .scalar_one()
    )
    if owed:
        raise RuntimeError(f"{owed} refunds are still owed; settle them before downgrading")
    op.drop_column("orders", "request_hash")
    op.drop_index("ix_payments_refund_pending", table_name="payments")
    _statuses(_OLD)
