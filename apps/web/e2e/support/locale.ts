/**
 * Сайтын анхдагч хэл монгол. Тестүүд англи бичвэр шалгадаг тул англи хэлийг `NEXT_LOCALE` cookie-гоор
 * тогтооно. Тест өөрөө context үүсгэх бүрдээ (`browser.newContext`) энэ cookie-г өгөх ёстой: төслийн
 * `storageState` зөвхөн Playwright-ийн өөрийн `context` fixture-д үйлчилнэ.
 */
const host = new URL(process.env.E2E_BASE_URL ?? "http://localhost:3000").hostname;

export const ENGLISH_COOKIE = {
  name: "NEXT_LOCALE",
  value: "en",
  domain: host,
  path: "/",
  expires: -1,
  httpOnly: false,
  secure: false,
  sameSite: "Lax" as const,
};

type Cookie = typeof ENGLISH_COOKIE;

/** Англи хэлтэй, өөр cookie-гүй `storageState`. */
export const ENGLISH = { cookies: [ENGLISH_COOKIE], origins: [] as never[] };

/** Нэвтэрсэн хэрэглэгчийн cookie-д англи хэлийг нэмсэн `storageState`. */
export function withEnglish(cookies: Omit<Cookie, never>[] | readonly object[]) {
  return { cookies: [...(cookies as Cookie[]), ENGLISH_COOKIE], origins: [] as never[] };
}
