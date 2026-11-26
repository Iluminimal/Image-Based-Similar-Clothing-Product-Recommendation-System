import { useLocale } from "next-intl";
import { DEFAULT_LOCALE, INTL_LOCALE, isLocale } from "@/i18n/config";
import { formatDate } from "@/i18n/dates";

/** Огноо, цаг дэлгүүрийн цагаар, тайлан болон CSV-тэй адил: "Oct 8, 2026, 10:00 AM" (идэвхтэй хэлээр). */
export const when = (iso: string, tag = "en-US") => formatDate(iso, { dateStyle: "medium", timeStyle: "short" }, tag);

/** "Oct 8, 2026" хэлбэр (идэвхтэй хэлээр). */
export const day = (iso: string, tag = "en-US") => formatDate(iso, { dateStyle: "medium" }, tag);

/** Идэвхтэй хэлний `when`/`day`: хэл солигдоход огноо нь дагана. */
export function useDates() {
  const locale = useLocale();
  const tag = INTL_LOCALE[isLocale(locale) ? locale : DEFAULT_LOCALE];
  return { when: (iso: string) => when(iso, tag), day: (iso: string) => day(iso, tag) };
}
