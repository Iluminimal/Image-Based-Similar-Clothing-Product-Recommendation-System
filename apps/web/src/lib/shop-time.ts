/**
 * Дэлгүүрийн өдөр. API тайлангийн өдрийн хилийг `SHOP_TIMEZONE`-оор тогтоодог тул web-ийн "өнөөдөр"
 * ч мөн адил байх ёстой (UTC-ийнх бол Улаанбаатарт 00:00-08:00 цагт өнөөдрийг сонгож чадахгүй).
 * Deploy дээр хоёулаа `.env.prod`-ийн `SHOP_TIMEZONE`-оос ирнэ.
 */
export const SHOP_TIME_ZONE = process.env.NEXT_PUBLIC_SHOP_TIMEZONE || "Asia/Ulaanbaatar";

/** Дэлгүүрийн цагаар өнөөдөр, `YYYY-MM-DD`. */
export function shopToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: SHOP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
