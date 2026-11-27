"""Монгол хаяг (хороо), төгрөгийн үнэ: addresses.khoroo; USD үнийг төгрөг рүү шилжүүлнэ

Revision ID: b8d4e6a1c3f2
Revises: a3f7c1d9e2b4
Create Date: 2026-11-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d4e6a1c3f2"
down_revision: str | Sequence[str] | None = "a3f7c1d9e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Schema болон өгөгдлийг шинэчилнэ."""
    op.add_column("addresses", sa.Column("khoroo", sa.String(length=40), nullable=True))
    op.alter_column("addresses", "postal_code", server_default="")
    # Дэлгүүр зөвхөн Монголд хүргэдэг болох тул гадаад улсын хадгалсан хаягуудыг устгана. Захиалга
    # дээрх хаягийн snapshot тусдаа хадгалагддаг тул өөрчлөгдөхгүй.
    op.execute("DELETE FROM addresses WHERE country <> 'MN'")

    # Үнийг USD cent-ээс төгрөг рүү `ingestion/pricing.py`-тэй ижил томьёогоор шилжүүлнэ: доллар x
    # 3.5 мянган төгрөг, хамгийн багадаа 10 мянга, төгсгөл нь `…900` (жишээ нь $25 -> 87,900 ₮).
    # Төгрөгийг бага нэгжээр (x 100) хадгалахад тоо USD cent-ээс хэдэн мянга дахин том болно. int4-д
    # багтахгүй байж болзошгүй тул эхлээд баганыг BigInteger болгоно.
    for table, column in (
        ("products", "price_cents"),
        ("orders", "subtotal_cents"),
        ("orders", "shipping_cents"),
        ("orders", "total_cents"),
        ("order_items", "unit_price_cents"),
        ("payments", "amount_cents"),
    ):
        op.alter_column(table, column, type_=sa.BigInteger(), existing_nullable=False)
    op.execute(
        "UPDATE products SET "
        "price_cents = (GREATEST(10, FLOOR(ROUND(price_cents / 100.0) * 3.5 + 0.5)::bigint) "
        "* 1000 - 100) * 100, "
        "currency = 'MNT' WHERE currency = 'USD'"
    )
    op.alter_column("products", "currency", server_default="MNT")


def downgrade() -> None:
    """Schema-г буцаана. Үнэ болон устгасан хаягийг сэргээхгүй (өгөгдөл алдагдсан)."""
    # Баганууд BigInteger хэвээр үлдэнэ: int4 руу буцаавал том тоо багтахгүй байх эрсдэлтэй.
    op.alter_column("products", "currency", server_default="USD")
    op.alter_column("addresses", "postal_code", server_default=None)
    op.drop_column("addresses", "khoroo")
