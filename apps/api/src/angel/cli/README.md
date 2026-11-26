# `cli`: командын мөрийн хэрэгслүүд

| Файл | Команд |
| --- | --- |
| `admin.py` | `make create-admin`, `make create-warehouse` (EMAIL=…), утсаа алдсан ажилтны 2FA-г арилгах |
| `outbox.py` | `make outbox`, `make outbox-retry` |
| `seed_demo.py` | `make seed-demo`, `make seed-demo-clean` |
| `clean_test_data.py` | `make clean-test-data` (анхдагчаар зөвхөн тоолно) |
| `openapi.py` | `make openapi` |

Ажилтны бүртгэлийг зөвхөн эндээс үүсгэнэ: вэбээр бүртгүүлсэн хүн үргэлж хэрэглэгч болно.

**Команд нэмэх:** энд модуль нэмж, `Makefile`-д тайлбартай (`##`) мөр бичнэ.
