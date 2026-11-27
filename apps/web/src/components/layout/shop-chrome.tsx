"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * Админ хэсгээс бусад хуудсыг хүрээлсэн дэлгүүрийн хэсгүүд: хэлний banner, header, үндсэн агуулга, footer.
 * Админ хэсэг өөрийн shell-тэй (sidebar-тай, дэлгүүрийн цэс, footer байхгүй). Header, footer-ийг server дээр
 * render хийж props-оор дамжуулдаг тул энэ component зөвхөн тэднийг харуулах эсэхийг шийднэ.
 */
export function ShopChrome({
  banner,
  header,
  footer,
  children,
}: {
  banner?: ReactNode;
  header: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  if (pathname === "/admin" || pathname.startsWith("/admin/"))
    return <>{children}</>;
  return (
    <>
      {banner}
      {header}
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
      {footer}
    </>
  );
}
