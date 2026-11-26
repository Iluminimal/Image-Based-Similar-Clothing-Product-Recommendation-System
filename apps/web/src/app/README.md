# `app`: хуудсууд

Folder бүр нэг URL. Энд зөвхөн чиглүүлэлт ба хуудасны metadata байна: `page.tsx` нь ихэвчлэн
`features/`-ийн нэг компонентыг харуулах хэдхэн мөр.

- Анхдагчаар Server Component. State, effect, browser API хэрэгтэй үед л `"use client"` бичнэ.
- `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx` нь Next.js-ийн тусгай файлууд.
- `admin/layout.tsx` ажилтан биш хүнийг админ хэсэгт оруулахгүй (жинхэнэ хамгаалалт API талд).

**Хуудас нэмэх:** `app/<url>/page.tsx`. Next.js-ийн энэ хувилбар өмнөхөөсөө ялгаатай тул эхлээд
`node_modules/next/dist/docs/`-ыг шалгана.
