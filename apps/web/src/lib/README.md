# `lib`: суурь код

| Файл, folder | Үүрэг |
| --- | --- |
| `api/` | API client, алдааг хэрэглэгчийн бичвэр болгох. `schema.d.ts` нь автоматаар үүсдэг тул **гараар засахгүй** (`make api-types`) |
| `env.ts` | Нийтийн орчны хувьсагч (шинийг нэмбэл `.env.example`-ийг шинэчилнэ) |
| `query-client.ts`, `query-keys.ts` | TanStack Query-ийн тохиргоо, түлхүүрүүд |
| `security-headers.ts` | CSP ба бусад header |
| `shop-time.ts` | Дэлгүүрийн цагийн бүсийн "өнөөдөр" |
| `image-loader.ts` | Барааны зургийн тохирох хэмжээг сонгох |
| `site.ts` | Сайтын нийтийн хаяг |

API дуудахдаа: server компонентод `api/client.ts`, browser дээр нэвтэрсэн хүний нэрийн өмнөөс бол
`api/browser.ts`.
