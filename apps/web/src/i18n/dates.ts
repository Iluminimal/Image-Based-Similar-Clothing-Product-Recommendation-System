/**
 * Огноог идэвхтэй хэлээр, дэлгүүрийн цагаар бичнэ.
 *
 * Монгол огноог `Intl`-ээр биш өөрсдөө угсарна: Chrome (Chromium) монгол огнооны өгөгдөлгүй тул
 * "Nov 3, 2026" гэж англиар гаргадаг. Server (Node) нь монголоор зурдаг байсан учир хуудас хөтөч дээр
 * ажиллаж эхлэхэд бичвэр зөрж, hydration алдаа гардаг байв. Цагийн бүсийг ч тогтмол өгнө: server,
 * хөтөч хоёр өөр бүсэд байсан ч ижил өдөр гарна.
 */
import { SHOP_TIME_ZONE } from "@/lib/shop-time";

/** CLDR-ийн монгол товчлол, `Date#getUTCDay`-ийн дарааллаар (ням гарагаас). */
const MN_WEEKDAYS = ["Ня", "Да", "Мя", "Лх", "Пү", "Ба", "Бя"];

export function formatDate(value: string | number | Date, options: Intl.DateTimeFormatOptions, tag: string): string {
  const zoned = { timeZone: SHOP_TIME_ZONE, ...options };
  const date = new Date(value);
  if (!tag.startsWith("mn")) return new Intl.DateTimeFormat(tag, zoned).format(date);

  // Тоонуудыг бүх орчинд байдаг англи өгөгдлөөр, тухайн бүсээр нь задалж авна.
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zoned.timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)!.value;

  // `dateStyle` бүх хэлбэрт, мөн юу ч заагаагүй үед жилтэй бүтэн огноо. Зөвхөн сар, өдөр хүссэн бол жилгүй.
  const withYear = options.dateStyle !== undefined || options.year !== undefined || options.month === undefined;
  let text = `${part("month")}-р сарын ${part("day")}`;
  if (withYear) text = `${part("year")} оны ${text}`;
  if (options.weekday !== undefined) {
    const weekday = new Date(Date.UTC(Number(part("year")), Number(part("month")) - 1, Number(part("day")))).getUTCDay();
    text = `${text}. ${MN_WEEKDAYS[weekday]}`;
  }
  if (options.timeStyle !== undefined || options.hour !== undefined) {
    text = `${text}, ${part("hour")}:${part("minute")}`;
  }
  return text;
}
