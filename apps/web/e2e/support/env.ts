export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin12345";
export const WAREHOUSE_EMAIL = process.env.E2E_WAREHOUSE_EMAIL ?? "warehouse@example.com";
export const WAREHOUSE_PASSWORD = process.env.E2E_WAREHOUSE_PASSWORD ?? "warehouse12345";
export const PASSWORD = "correct horse battery staple";
/**
 * API EMBEDDER=fake-тэй (CI) ажиллаж байвал үнэн. Browser upload бүрийг дахин encode хийдэг. Жинхэнэ model-д
 * энэ хамаагүй ч pixel яг таарахыг шаарддаг fake үүнийг даахгүй. Тиймээс UI тестүүд дахин encode хийсэн
 * зургаар аль бараа олдохыг шалгахгүй; API тестүүд анхны byte-аар шалгасаар байна.
 */
export const FAKE_MODEL = process.env.E2E_FAKE_MODEL === "1";
/** API LOCALIZER=fake-тэй (CI) үнэн: зургийг дээд ("top") ба доод ("shoe") хоёр хэсэг болгоно. */
export const FAKE_LOCALIZER = process.env.E2E_FAKE_LOCALIZER === "1";
