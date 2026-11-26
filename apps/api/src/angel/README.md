# `angel`: backend

FastAPI-ийн код. Бүтцийн бүтэн тайлбар: [`docs/architecture.md`](../../../../docs/architecture.md).

Хүсэлт нэг чиглэлд явна: `api` → `services` → `repositories` → `models`. Давхарга бүр зөвхөн доорхоо
дуудна.

| Folder, файл | Юу байдаг |
| --- | --- |
| [`api/`](api/README.md) | HTTP route-ууд |
| [`services/`](services/README.md) | Дэлгүүрийн дүрэм |
| [`repositories/`](repositories/README.md) | SQL query |
| [`models/`](models/README.md) | Өгөгдлийн сангийн хүснэгтүүд (ORM) |
| [`schemas/`](schemas/README.md) | Хүсэлт, хариуны хэлбэр (Pydantic) |
| [`core/`](core/README.md) | Тохиргоо, аюулгүй байдал, алдаа зэрэг нийтлэг хэсэг |
| [`ml/`](ml/README.md) | Зургийн embedding, хувцас таних |
| [`ingestion/`](ingestion/README.md) | Датасетийг ачаалах |
| [`payments/`](payments/README.md) | Төлбөрийн gateway |
| [`cli/`](cli/README.md) | Командын мөрийн хэрэгслүүд |
| `oauth/` | Google-ээр нэвтрэх provider (жинхэнэ ба хиймэл) |
| `db/` | SQLAlchemy-ийн engine, `Base` класс |
| `storage.py` | Барааны зураг хадгалах интерфейс |
| `main.py` | Аппыг угсрах газар |

`api`, `services`, `repositories`, `schemas` дотор ижил нэртэй хэсгүүд бий: `accounts`, `catalog`, `commerce`,
`reviews`, `admin`, `system`. Нэг боломжийн код давхарга бүрд ижил нэртэй folder-т байна. Тестүүд
(`apps/api/tests/`) ч мөн адил хуваагдсан.
