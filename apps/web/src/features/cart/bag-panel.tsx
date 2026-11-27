"use client";

import { useTranslations } from "next-intl";
import { LogIn, X } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Dialog } from "radix-ui";
import type { ReactNode, RefObject } from "react";
import { useBarPanel } from "@/components/layout/bar-panel";
import { HEADER_CELL } from "@/components/layout/header-cell";
import { accountLinks } from "@/features/auth/account-links";
import { useAuth } from "@/features/auth/auth-store";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { MiniCartSkeleton } from "./mini-cart";

// Сагсны жагсаалт, тоо өөрчлөх товч, mutation-уудыг хэрэглэгч сагсаа нээх үед л татна.
const MiniCart = dynamic(() => import("./mini-cart").then((m) => m.MiniCart), {
  ssr: false,
  loading: () => <MiniCartSkeleton />,
});

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  count: number;
  /** Самбарыг нээсэн товч: хаахад focus түүн рүү буцна. */
  trigger: RefObject<HTMLButtonElement | null>;
};

/**
 * apple.com шиг Bag: том гарчигтай цул хуудас. Барааны жагсаалт bar-ын logo-той нэг шугамд, доор нь профайл
 * руу очих холбоосууд (утсан дээр account энд байдаг, цэсэнд биш).
 * md-ээс дээш бол bar-ын доорх бүх хэсгийг эзэлж, bar-ыг хэвээр ашиглаж болно: bag товч дахин дарахад
 * хаагдана, search эсвэл department цэс нээхэд ч хаагдана (modal биш dialog). Утсан дээр бүтэн дэлгэцийг
 * бүрхэнэ. Header-ийн бусад товч харагдахгүй тул өөрийн bar-тай, зөвхөн хаах товчтой.
 * Анх нээхэд л ачаална (`CartButton`-г үзнэ үү): bag icon харуулахад dialog library хэрэггүй.
 */
export function BagPanel({ open, onOpenChange, count, trigger }: Props) {
  const t = useTranslations("cart");
  const tn = useTranslations("account.nav");
  const close = () => onOpenChange(false);
  useBarPanel(open);
  // md-ээс дээш bar болон ард нь байгаа хуудсыг ашиглаж болсоор байна. Утсан дээр бүтэн дэлгэцийг бүрхдэг тул
  // dialog modal болно.
  const wide = useMediaQuery("(min-width: 768px)");
  const signedIn = useAuth((state) => state.status === "signedIn");
  const role = useAuth((state) => state.user?.role);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={!wide}>
      <Dialog.Portal>
        <Dialog.Content
          className="bag-flyout bg-background fixed inset-0 z-50 flex flex-col overflow-y-auto overscroll-contain outline-none duration-300 max-md:data-closed:animate-out max-md:data-closed:fade-out-0 max-md:data-open:animate-in max-md:data-open:fade-in-0 max-md:data-open:slide-in-from-top-4 md:top-[2.8125rem] md:bottom-auto md:z-30 md:max-h-[calc(100dvh-2.8125rem)] md:bg-[var(--flyout)]"
          // Bar дээрх товчийг (department, search, bag) дарахад тэр товч өөрөө хариуцна.
          onInteractOutside={(event) => {
            if ((event.target as Element).closest("header")) event.preventDefault();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            trigger.current?.focus();
          }}
        >
          {/* Утсан дээр энэ хуудас bar-ыг бүрхдэг тул өөрийн X товчтой. md-ээс дээш bar харагдсаар байна. */}
          <div className="container-nav w-full md:hidden">
            <div className="flex h-12 items-center justify-end">
              <Dialog.Close className={HEADER_CELL} aria-label={t("closeBag")}>
                <X className="size-[18px]" strokeWidth={1.25} />
              </Dialog.Close>
            </div>
          </div>
          <div className="container-nav flex w-full flex-1 flex-col pt-6 pb-16 md:pt-10 md:pb-20">
            <div className="flex w-full max-w-2xl flex-1 flex-col">
              <Dialog.Title className={cn("type-display mb-8 md:mb-6 md:text-2xl md:leading-7 md:font-semibold md:tracking-normal", count === 0 && "md:sr-only")}>
                {t("bag")}
                {count > 0 && <span className="text-muted-foreground ml-3 font-normal">{count}</span>}
              </Dialog.Title>
              <Dialog.Description className="sr-only">{t("bagDescription")}</Dialog.Description>
              <MiniCart onNavigate={close} />
              <nav aria-label={t("profile")} className="border-border mt-12 border-t pt-8 md:mt-10 md:border-t-0 md:pt-0">
                <p className="text-muted-foreground mb-3 type-caption">{t("profile")}</p>
                <ul className="space-y-1">
                  {signedIn ? (
                    accountLinks(role).map(({ href, key, icon: Icon }) => (
                      <li key={href}>
                        <ProfileLink href={href} onClick={close}>
                          <Icon aria-hidden className="text-muted-foreground size-4" /> {tn(key)}
                        </ProfileLink>
                      </li>
                    ))
                  ) : (
                    <li>
                      <ProfileLink href="/login" onClick={close}>
                        <LogIn aria-hidden className="text-muted-foreground size-4" /> {t("signIn")}
                      </ProfileLink>
                    </li>
                  )}
                </ul>
              </nav>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Профайлын жагсаалтын нэг мөр: жижиг icon, тод нэр, apple.com-ийн Bag-ийн доод хэсэг шиг. */
function ProfileLink({ href, onClick, children }: { href: string; onClick: () => void; children: ReactNode }) {
  return (
    <Link
      href={href}
      onClick={onClick}
      // Нэвтрээгүй зочныг account хуудас redirect хийдэг. Prefetch хийвэл тэр redirect cache-д үлдэж,
      // нэвтэрсний дараа ч дахин давтагдана.
      prefetch={false}
      className="hover:text-brand focus-visible:ring-ring/50 -mx-2 flex items-center gap-3 rounded-md px-2 py-2 type-intro font-semibold tracking-tight outline-none transition-colors focus-visible:ring-3 md:py-1.5 md:type-fine md:leading-4 md:tracking-normal"
    >
      {children}
    </Link>
  );
}
