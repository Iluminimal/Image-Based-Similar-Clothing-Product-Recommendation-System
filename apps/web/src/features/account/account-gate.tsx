"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/features/auth/auth-store";
import { useIsStaff } from "@/features/auth/use-role";

/**
 * /account/* : `proxy.ts` зөвхөн session cookie байгаа эсэхийг шалгадаг. Cookie хуучирсан (refresh
 * татгалзсан) бол хуудас API-ийн алдааны текст харуулахын оронд нэвтрэх хуудас руу явуулж, нэвтэрсний
 * дараа энд буцаана.
 */
export function AccountGate({ children }: { children: ReactNode }) {
  const status = useAuth((state) => state.status);
  const router = useRouter();
  const pathname = usePathname();
  const isStaff = useIsStaff();
  // Захиалга, хадгалсан бараа, хаяг нь худалдан авагчийнх: ажилтанд зөвхөн профайл.
  const shopperPage = isStaff && !pathname.startsWith("/account/profile");
  useEffect(() => {
    if (status === "signedOut") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (shopperPage) router.replace("/account/profile");
  }, [status, shopperPage, pathname, router]);
  return status === "signedOut" || shopperPage ? null : children;
}
