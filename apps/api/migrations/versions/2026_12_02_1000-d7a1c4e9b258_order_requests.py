"""цуцлах, буцаах хүсэлт

Revision ID: d7a1c4e9b258
Revises: c5e2a8f4b913
Create Date: 2026-12-02 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a1c4e9b258"
down_revision: str | Sequence[str] | None = "c5e2a8f4b913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPEN = "status IN ('requested', 'approved', 'received')"


def upgrade() -> None:
    """Schema-г шинэчилнэ."""
    op.create_table(
        "order_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="requested", nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("details", sa.String(length=500), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("restocked", sa.Boolean(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('cancel', 'return')", name=op.f("ck_order_requests_kind_valid")
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'received', 'completed', 'declined', 'withdrawn')",
            name=op.f("ck_order_requests_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_requests_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_requests")),
    )
    op.create_index("ix_order_requests_order_id", "order_requests", ["order_id"])
    op.create_index(
        "uq_order_requests_one_open",
        "order_requests",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN),
    )
    op.create_index(
        "ix_order_requests_open_status",
        "order_requests",
        ["status", "kind"],
        postgresql_where=sa.text(_OPEN),
    )


def downgrade() -> None:
    """Schema-г буцаана. Шийдэгдээгүй хүсэлт байвал алдахгүйн тулд зогсоно."""
    waiting = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM order_requests "
                "WHERE status IN ('requested', 'approved', 'received')"
            )
        )
        .scalar_one()
    )
    if waiting:
        raise RuntimeError(f"{waiting} requests are still open; close them before downgrading")
    op.drop_table("order_requests")
