/**
 * Нийтийн тохиргоог апп эхлэхэд нэг удаа шалгана. Ингэснээр буруу хаяг canonical холбоос, Open Graph tag,
 * sitemap-д орохын оронд тэр даруй ил алдаа гарна. Зориуд энгийн TypeScript-ээр бичсэн: browser-ийн код энэ
 * модулийг import хийдэг тул хоёр string шалгахын тулд validation сан зочин бүрд татагдах ёсгүй.
 */

function publicUrl(name: string, value: string | undefined, fallback: string): string {
  const url = value || fallback;
  try {
    const { protocol } = new URL(url);
    if (protocol !== "http:" && protocol !== "https:") throw new Error("not http(s)");
  } catch {
    throw new Error(`${name} must be a full http(s) URL such as ${fallback}, got "${url}"`);
  }
  return url.replace(/\/+$/, "");
}

// Next.js зөвхөн статикаар заасан NEXT_PUBLIC_* хувьсагчийг inline болгодог тул тус бүрийг энд
// нэрлэж бичих ёстой, `process.env`-ийг бүхлээр нь дамжуулж болохгүй.
export const env = {
  NEXT_PUBLIC_API_URL: publicUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000"),
  NEXT_PUBLIC_SITE_URL: publicUrl("NEXT_PUBLIC_SITE_URL", process.env.NEXT_PUBLIC_SITE_URL, "http://localhost:3000"),
};
