"""ажилтны хоёр шатлалт нэвтрэлт, дахин баталгаажуулах код

Revision ID: b3c8d1f6a247
Revises: a9d3e5f7b126
Create Date: 2026-11-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3c8d1f6a247"
down_revision: str | Sequence[str] | None = "a9d3e5f7b126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "'login', 'verify_email', 'verify_phone', 'change_email', 'change_phone', 'reset_password'"


def _purposes(values: str) -> None:
    op.drop_constraint(op.f("ck_otp_challenges_purpose_valid"), "otp_challenges")
    op.create_check_constraint(
        op.f("ck_otp_challenges_purpose_valid"), "otp_challenges", f"purpose IN ({values})"
    )


def upgrade() -> None:
    """Schema-г шинэчилнэ."""
    op.add_column("users", sa.Column("totp_secret", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_recovery_hashes", postgresql.ARRAY(sa.String(length=64)), nullable=True),
    )
    _purposes(f"{_OLD}, 'reauth'")
    # Ажилтныг зөвхөн сервер дээрх command үүсгэдэг тул хаягийг нь оператор баталсан гэж үзнэ.
    # Баталгаажаагүй үлдвэл кодоор нэвтрэх, Google холбох дүрэм нууц үгийг нь устгаж болох байсан.
    op.execute(
        "UPDATE users SET email_verified_at = now() "
        "WHERE role IN ('admin', 'warehouse') AND email IS NOT NULL AND email_verified_at IS NULL"
    )


def downgrade() -> None:
    """Schema-г буцаана."""
    op.execute("DELETE FROM otp_challenges WHERE purpose = 'reauth'")
    _purposes(_OLD)
    op.drop_column("users", "totp_recovery_hashes")
    op.drop_column("users", "totp_last_step")
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_secret")
