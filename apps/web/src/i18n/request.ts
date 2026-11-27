import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale, type Locale } from "./config";

/** Cookie-д хадгалсан сонголт, үгүй бол монгол хэл (хөтчийн `Accept-Language`-г тоохгүй). */
async function resolveLocale(): Promise<Locale> {
  const saved = (await cookies()).get(LOCALE_COOKIE)?.value;
  return isLocale(saved) ? saved : DEFAULT_LOCALE;
}

// `getTranslations({ locale })` шиг хэл тодорхой заасан бол (жишээ нь санал болгож буй хэлээр бичсэн хэл
// солих banner) тэр хэлийг ашиглана.
export default getRequestConfig(async ({ locale: requested }) => {
  const locale = isLocale(requested) ? requested : await resolveLocale();
  const messages = await import(`../../messages/${locale}`).then((module) => module.default);
  return { locale, messages };
});
