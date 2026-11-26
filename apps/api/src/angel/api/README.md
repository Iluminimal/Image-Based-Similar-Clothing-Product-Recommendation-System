# `api`: HTTP route-ууд

Route нь хүсэлтийг шалгаж, service-ийг дуудаж, schema буцаана. **Дүрэм, SQL энд бичихгүй.**

- `v1/<хэсэг>/` — `/api/v1` доорх endpoint-ууд. `v1/router.py` бүгдийг нэгтгэнэ.
- `v1/admin/__init__.py` — админ ба агуулахын бүх route-ийн өмнөх нийтлэг хамгаалалт (хүсэлтийн хязгаар,
  ажилтан мөн эсэх, cache хийхгүй). Аль role юу хийхийг endpoint бүр өөрөө заана: `AdminDep`,
  `WarehouseDep`, `StaffDep`.
- `health.py` — `/healthz`, `/readyz` (хувилбаргүй).

**Endpoint нэмэх:** route (энд) → дүрэм (`services/`) → query (`repositories/`) → хэлбэр (`schemas/`) →
тест (`apps/api/tests/`). Дараа нь `make api-types` ажиллуулж вэбийн төрлийг шинэчилнэ. Шинэ service
хэрэгтэй бол `core/deps.py`-д угсарна.
