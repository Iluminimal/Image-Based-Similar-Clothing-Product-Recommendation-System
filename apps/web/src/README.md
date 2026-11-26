# `src`: вэб аппын код

Next.js (App Router). Бүтцийн бүтэн тайлбар: [`docs/architecture.md`](../../../docs/architecture.md).

| Folder, файл | Юу байдаг |
| --- | --- |
| [`app/`](app/README.md) | URL бүрийн хуудас |
| [`features/`](features/README.md) | Боломж бүрийн код |
| [`components/`](components/README.md) | Хэд хэдэн боломжид нийтлэг UI |
| [`lib/`](lib/README.md) | API client, тохиргоо, туслах функц |
| [`i18n/`](i18n/README.md) | Хэл: монгол (анхдагч), англи |
| `styles/` | Нүүр хуудасны загвар, хөдөлгөөний CSS (нийтлэг нь `app/globals.css`) |
| `test/` | Unit тестийн туслахууд |
| `proxy.ts` | Хуудас бүрийн өмнө ажиллана: нэвтрэлтийн эхний шалгалт, CSP |

Бичвэрийг компонентод шууд бичихгүй: `apps/web/messages/mn` ба `en` хоёуланд нь нэмнэ.
