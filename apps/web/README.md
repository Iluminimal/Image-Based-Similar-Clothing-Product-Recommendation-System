# Angel web

Next.js 16 (App Router) + React 19 + TypeScript (strict) + Tailwind v4 + shadcn/ui.
Суулгах заавар үндсэн [README](../../README.md)-д байна. Repository-ийн root-оос `make web` гэж ажиллуулна.

```bash
npm run dev         # хөгжүүлэлтийн server :3000
npm run lint
npm run typecheck   # next typegen && tsc --noEmit
npm test            # Vitest + Testing Library
npm run build
```

```bash
make api-types      # API-ийн OpenAPI-аас src/lib/api/schema.d.ts-ийг дахин үүсгэнэ (commit хийгддэг)
make web-prod       # production build-ийг :3000 дээр ажиллуулна (e2e, Lighthouse үүнийг хэмждэг)
make e2e            # Playwright end-to-end тест (docs/e2e.md)
make lighthouse     # production build дээрх Lighthouse (үр дүн, арга: docs/frontend.md)
```

## Folder бүтэц

Folder бүрийн заавар тухайн folder-ийн `README.md`-д бий (эхлэх нь: [`src/README.md`](src/README.md)).

- `src/app` — route ба layout-ууд. Анхдагчаар Server Component; client талын provider-ууд `providers.tsx`-д бий.
  Дэлгүүр, бүртгэл, checkout хуудсууд, `/admin/*` (админ ба агуулахын ажилтан, `docs/admin.md`), `sitemap.ts`, `robots.ts`.
  Нүүр, хайлтын хуудсыг хүсэлт бүрд шинээр зурна: эдгээр нь API-аас уншдаг, харин build хийх үед API ажиллаагүй байдаг.
- `src/features/<нэр>` — боломж бүрийн код (component, API дуудлага, тест нэг дор):
  `catalog` (жагсаалт, шүүлтүүр, барааны хуудас), `search` (зургаар хайх), `home`, `cart`, `checkout`, `account`,
  `orders`, `reviews`, `wishlist`, `auth`, `admin`, `seo`.
- `src/components/ui` — shadcn/ui-ийн суурь хэсгүүд (шинэ нэмэх: `npx shadcn@latest add <нэр>`).
- `src/lib/api` — OpenAPI-аас үүссэн төрлүүд (`schema.d.ts`), төрөлтэй `openapi-fetch` клиент, RFC 7807 алдааны боловсруулалт.
- `src/lib/image-loader.ts` — API-ийн урьдчилан үүсгэсэн 400/800 px WebP-г сонгож, энэ сайтын `/media` route-оор дамжуулна.
  Тиймээс Next-ийн зургийн optimizer ашиглагддаггүй.
- `src/lib/env.ts` — шалгагдсан орчны хувьсагчид (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `.env.example`-ийг харна).
  Browser-ийн код үүнийг import хийдэг тул зориуд сан ашиглалгүй, энгийн TypeScript-ээр бичсэн.
- `e2e/` — Playwright тестүүд, `scripts/lighthouse.mjs` — Lighthouse скрипт.

## Анхаарах зүйл

- Хуудсан дээр давхарлан нээгддэг хэсгүүдийг (dialog, sheet, dropdown) анх хэрэгтэй болоход нь `next/dynamic`-аар
  ачаална. Scroll-snap container-д `scroll-smooth` нэмж болохгүй. Хоёр дүрмийн шалтгаан `docs/frontend.md`-ийн
  Performance хэсэгт бий.
- Dark mode `<html>` дээрх `dark` class-аар асдаг (`components/theme`). Анхдагч нь цайвар; хэрэглэгч харанхуй
  горим эсвэл системийн тохиргоог дагахыг сонгож болно.
- Tailwind нь PostCSS plugin-оор (`postcss.config.mjs`) ажиллана.
