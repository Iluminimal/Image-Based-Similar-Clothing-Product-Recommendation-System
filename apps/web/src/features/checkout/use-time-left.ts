"use client";

import { useEffect, useState } from "react";

/**
 * `expiresAt` хүртэл үлдсэн секунд (секунд бүр шинэчлэгдэнэ). Хугацаа тодорхойгүй бол null. Сервер,
 * browser-ийн цаг зөрж болох тул `expiresAt`-ийг шууд харуулахгүй, зөвхөн үлдсэн хугацаа тоолоход хэрэглэнэ.
 */
export function useTimeLeft(expiresAt: string | null | undefined): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!expiresAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt]);
  if (!expiresAt) return null;
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - now) / 1000));
}

/** 1805 -> "30:05". */
export function formatTimeLeft(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
