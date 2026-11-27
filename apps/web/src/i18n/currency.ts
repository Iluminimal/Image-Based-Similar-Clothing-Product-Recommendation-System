/**
 * Дэлгүүрийн цорын ганц валют нь төгрөг (Amazon, Apple зах зээл бүрдээ орон нутгийн валютаар үнэлдэг
 * шиг). Үнэ API-д бага нэгжээр (төгрөг x 100) ирнэ. Ханшийн хөрвүүлэлт байхгүй: харуулсан дүн яг
 * төлөх дүн.
 */
export const BASE_CURRENCY = "MNT";

/**
 * Мөнгөн дүнг харуулах: төгрөг бутархайгүй, "₮" тэмдэг урд нь ("₮125,383"). Төгрөгийг `Intl`-ээр биш өөрсдөө
 * угсарна: server (Node), browser хоёрын ICU өгөгдөл төгрөгийн тэмдгийн ард зайг өөрөөр тавьдаг тул hydration
 * алдаа гардаг байсан. Тоог "en-US"-ийн адил таслалаар бүлэглэнэ (монгол бичгийнхтэй ижил), орчин бүрд
 * адилхан гарна. Бусад валютыг (хуучин USD захиалга) өөрийн бутархайтай нь `Intl`-ээр бичнэ.
 */
export function formatMoney(minor: number, currency: string, tag: string): string {
  if (currency === "MNT") {
    const whole = Math.round(Math.abs(minor) / 100);
    return `${minor < 0 ? "-" : ""}₮${whole.toLocaleString("en-US")}`;
  }
  return new Intl.NumberFormat(tag, {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: minor % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(minor / 100);
}
