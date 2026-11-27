# `features`: боломж бүрийн код

Нэг боломжийн компонент, өгөгдлийн hook, API дуудлага, тест нэг folder-т байна:
`catalog`, `search`, `home`, `cart`, `checkout`, `orders`, `reviews`, `wishlist`, `account`, `auth`,
`admin` (админ ба агуулахын ажилтан), `seo`.

Түгээмэл нэршил:

- `*-api.ts` — API дуудлага.
- `use-*.ts` — hook. Серверийн өгөгдлийг TanStack Query-ээр авна.
- `*-store.ts` — зөвхөн UI-ийн state (Zustand).
- `*.test.tsx` — тест; шалгадаг файлынхаа хажууд байна.

Маягтад React Hook Form ба Zod ашиглана. Zod-ыг browser дээр ашигладаг файл эхэндээ
`import "@/lib/zod-jitless"` бичнэ.
