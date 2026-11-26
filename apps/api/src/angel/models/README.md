# `models`: хүснэгтүүд

SQLAlchemy-ийн ORM класс бүр нэг хүснэгт. Client руу ORM объект буцаахгүй, `schemas/` ашиглана.

**Хүснэгт, багана нэмэх:**

1. Энд model-оо өөрчилнө.
2. `cd apps/api && uv run alembic revision --autogenerate -m "…"`.
3. Үүссэн файлыг (`apps/api/migrations/versions/`) **заавал уншиж шалгана**: Alembic `CHECK` constraint
   зэрэг зарим зүйлийг анзаардаггүй.
4. `make migrate`, дараа нь `uv run alembic check` "No new upgrade operations" гэж хэлэх ёстой.

Мөнгөн дүнг бүхэл бага нэгжээр хадгална (төгрөг x 100; багана нь `*_cents` нэртэй). Цагийг UTC-ээр
хадгална.
