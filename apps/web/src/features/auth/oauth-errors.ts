import type { AuthTranslator } from "./auth-translator";

const CODES = ["google_denied", "google_failed", "google_unverified", "account_disabled"] as const;
type OAuthErrorCode = (typeof CODES)[number];

function isCode(code: string): code is OAuthErrorCode {
  return (CODES as readonly string[]).includes(code);
}

/**
 * `?error=` кодтойгоор login хуудас руу буцсан хүнд юу хэлэх вэ. Танихгүй кодод юу ч харуулахгүй: гадны
 * холбоос манай хуудсан дээр өөрийн бичвэрийг гаргаж чадах ёсгүй.
 */
export function oauthErrorMessage(raw: string | string[] | undefined, t: AuthTranslator): string | null {
  const code = Array.isArray(raw) ? raw[0] : raw;
  // Зөвхөн мэдэгдэх код: `?error=constructor` нь Object.prototype-ийнхыг олох ёсгүй.
  return code && isCode(code) ? t(`google.errors.${code}`) : null;
}
