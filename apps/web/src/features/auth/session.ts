/**
 * Browser дахь нэвтрэлт: refresh cookie-оор access token авах, сэргээх, дуусгах.
 *
 * Access token зөвхөн санах ойд (`auth-store.ts`) байдаг тул хуудсыг ачаалах бүрд эндээс сэргээнэ.
 */

import { useAuth } from "./auth-store";

const SESSION_COOKIE = "lk_session";

/** `lk_session` нь API httpOnly refresh cookie-ийн хажууд тавьдаг нууц биш тэмдэг. */
export function hasSessionCookie(): boolean {
  return (
    typeof document !== "undefined" &&
    document.cookie.split("; ").some((c) => c.startsWith(`${SESSION_COOKIE}=`))
  );
}

function dropSessionCookie() {
  document.cookie = `${SESSION_COOKIE}=; Max-Age=0; Path=/`;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

let inflight: Promise<boolean> | null = null;

/**
 * Refresh cookie-гоор шинэ access token авна. Нэг зэрэг дуудвал бүгд нэг хүсэлтийг хуваалцана. Refresh token
 * хэрэглэх бүрд солигддог тул хоёр refresh зэрэг явбал хоёр дахь нь ашигласан token-ыг давтсан мэт харагдана.
 */
export function refreshSession(): Promise<boolean> {
  inflight ??= attemptRefresh().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function attemptRefresh(): Promise<boolean> {
  let rejected = false;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.ok) {
        useAuth.getState().setSession(await response.json());
        return true;
      }
      if (response.status !== 401) break;
      rejected = true;
    } catch {
      break; // офлайн эсвэл API унасан: "гарсан" гэсэнтэй ижил биш
    }
    // Өөр tab cookie-г дөнгөж сая сольсон байж болно; дахин нэг оролдоход шинийг нь авна.
    if (attempt === 0) await sleep(150);
  }
  useAuth.getState().clear();
  if (rejected) dropSessionCookie();
  return false;
}

/** Ачаалахад нэг удаа дуудна: cookie-оос session сэргээх, эсвэл "гарсан" төлөвт тогтох. */
export async function bootstrapSession(): Promise<void> {
  if (useAuth.getState().status !== "unknown") return;
  if (hasSessionCookie()) await refreshSession();
  else useAuth.getState().clear();
}

export async function endSession(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
  } finally {
    useAuth.getState().clear();
    dropSessionCookie();
  }
}
