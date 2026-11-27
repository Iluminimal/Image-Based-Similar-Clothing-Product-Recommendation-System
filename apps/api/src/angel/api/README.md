# `api`: HTTP route-ууд

Route нь хүсэлтийг шалгаж, service-ийг дуудаж, schema буцаана. **Дүрэм, SQL энд бичихгүй.**

- `v1/<хэсэг>/` — `/api/v1` доорх endpoint-ууд. `v1/router.py` бүгдийг нэгтгэнэ.
- `v1/admin/__init__.py` — админ, агуулахын бүх route-д үйлчлэх хамгаалалт: хүсэлтийн хязгаар, ажилтан мөн
  эсэхийг шалгах, хариуг cache хийлгэхгүй байх. Ямар role хандахыг endpoint бүр өөрөө заана: `AdminDep`,
  `WarehouseDep`, `StaffDep`.
- `health.py` — `/healthz`, `/readyz` (`/api/v1` угтваргүй).

**Endpoint нэмэх:** route (энд) → дүрэм (`services/`) → query (`repositories/`) → хэлбэр (`schemas/`) →
тест (`apps/api/tests/`). Дараа нь `make api-types` ажиллуулж вэбийн төрлийг шинэчилнэ. Шинэ service
хэрэгтэй бол `core/deps.py`-д угсарна.
