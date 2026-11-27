import type { AuthTranslator } from "./auth-translator";
import { toE164 } from "./phone-input";
import type { CountryCode } from "libphonenumber-js/min";

/** "Имэйл эсвэл утас" гэсэн ганц талбарт хэрэглэгчийн бичсэн зүйл. */
export type Identifier =
  | { kind: "email"; destination: string; shown: string }
  | { kind: "phone"; destination: string; shown: string };

/**
 * Бичсэн зүйл зөвхөн утасны дугаар байж болох бол true: цифр, "+" эсвэл "("-ээр эхэлж, зөвхөн цифр, зай,
 * дугаарт хэрэглэдэг тэмдэгт агуулсан. Үсэг эсвэл "@" орсон бол имэйл гэж үзнэ; хоосон талбар ч мөн.
 */
export function looksLikePhone(text: string): boolean {
  return /^[+(\d][\d\s().+-]*$/.test(text.trim());
}

/**
 * Талбарт бичсэн имэйл эсвэл утасны дугаарыг API-ийн хүлээдэг хэлбэрт оруулна. Болохгүй бол шалтгааныг
 * буцаана.
 */
export function parseIdentifier(text: string, region: CountryCode, t: AuthTranslator): Identifier | { error: string } {
  const typed = text.trim();
  if (!typed) return { error: t("identifier.empty") };
  if (looksLikePhone(typed)) {
    const destination = toE164(typed, region);
    return destination ? { kind: "phone", destination, shown: typed } : { error: t("identifier.invalidPhone") };
  }
  const email = typed.toLowerCase();
  return /^\S+@\S+\.\S+$/.test(email)
    ? { kind: "email", destination: email, shown: typed }
    : { error: t("identifier.invalid") };
}
