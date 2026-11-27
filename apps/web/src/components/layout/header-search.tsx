"use client";

import { ArrowRight, X } from "lucide-react";
import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useVocab } from "@/i18n/use-vocab";
import { cn } from "@/lib/utils";
import { HEADER_CELL, SearchGlyph } from "@/components/layout/header-cell";
import { DEPARTMENT_LINKS, categoryHref } from "@/features/catalog/nav";
import { announceFlyout, useCloseOnOtherFlyout } from "./bar-flyout";
import { useBarPanel } from "./bar-panel";

// Хайлтын талбар, санал болголт, зураг сонгогч хайлт анх нээгдэхэд ачаалагдана.
const SearchBar = dynamic(() => import("./search-bar").then((m) => m.SearchBar), { ssr: false });

function QuickLinks({ onNavigate }: { onNavigate: () => void }) {
  const t = useTranslations("layout.header");
  const vocab = useVocab();
  const links = [
    ...DEPARTMENT_LINKS.map((d) => ({ href: categoryHref(d.slug), label: vocab.department(d.label) })),
    { href: "/products?sort=newest", label: t("newArrivals") },
    { href: "/search", label: t("searchWithPhoto") },
  ];
  return (
    <nav aria-label={t("quickLinks")} className="mt-8">
      <p className="flyout-item text-muted-foreground mb-3 type-fine" style={{ "--i": 1 } as CSSProperties}>
        {t("quickLinksHeading")}
      </p>
      <ul className="space-y-1 md:space-y-0">
        {links.map((link, i) => (
          <li key={link.href} className="flyout-item" style={{ "--i": i + 2 } as CSSProperties}>
            <Link
              href={link.href}
              onClick={onNavigate}
              className="hover:text-brand focus-visible:ring-ring/50 -mx-2 inline-flex items-center gap-3 rounded-md px-2 py-1 type-intro font-semibold tracking-tight outline-none transition-colors focus-visible:ring-3 md:py-1.5 md:type-fine md:leading-4 md:tracking-normal"
            >
              <ArrowRight aria-hidden strokeWidth={1.5} className="text-muted-foreground size-4 shrink-0 md:size-3" />
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * Apple-ийнх шиг хайлт: bar дээрх томруулагч том талбар, шуурхай холбоос бүхий panel нээнэ. md-ээс дээш бол
 * bar-ын доорх дэлгэцийг дүүргэж, bar харагдсаар үлдэнэ. Томруулагчийг дахин дарах, Escape дарах, өөр flyout
 * нээхэд хаагдана. Утсан дээр bar-ыг ч бүрхэж, зөвхөн X үлдэнэ. Panel-ийг <body> руу portal хийдэг:
 * header-ийн backdrop blur доторх `fixed` бүх элементийг өөртөө уяж орхидог.
 */
export function HeaderSearch() {
  const t = useTranslations("layout.header");
  const pathname = usePathname();
  // Аль хуудсан дээр нээснээ санана: өөр хуудас руу шилжвэл effect-гүйгээр хаагдсанд тооцогдоно.
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const open = openedAt !== null && openedAt === pathname;

  const close = () => setOpenedAt(null);
  useBarPanel(open);
  useCloseOnOtherFlyout("search", close);

  // Focus хаана ч байсан Escape panel-ийг хаана (focus panel дотор бол panel-ийн өөрийн handler барина).
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpenedAt(null);
      button.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // GitHub, apple.com шиг хаанаас ч "/" дарвал хайлт нээгдэнэ. Харин талбарт бичиж байх үед (тэнд "/" энгийн
  // тэмдэгт), dialog дотор, modifier товчтой хамт дарсан үед нээгдэхгүй.
  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented || event.isComposing) return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || target?.closest('input, textarea, select, [role="dialog"], [role="combobox"]')) return;
      event.preventDefault();
      setRequested(true);
      setOpenedAt(pathname);
      announceFlyout("search");
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pathname]);
  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
      button.current?.focus();
    }
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        className={cn(HEADER_CELL, "phone-bar-item")}
        aria-label={t("searchOpen")}
        title={t("searchTitle")}
        aria-keyshortcuts="/"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="search-panel"
        onClick={() => {
          setRequested(true);
          setOpenedAt(open ? null : pathname);
          if (!open) announceFlyout("search");
        }}
      >
        <SearchGlyph />
      </button>
      {requested &&
        createPortal(
          <>
            <div
              id="search-panel"
              role="dialog"
              aria-label={t("searchDialog")}
              data-open={open}
              inert={!open}
              onKeyDown={onKeyDown}
              className="search-panel bg-background fixed inset-x-0 top-0 z-50 h-dvh overflow-y-auto overscroll-contain pb-10 md:top-[2.8125rem] md:z-30 md:h-auto md:max-h-[calc(100dvh-2.8125rem)] md:bg-[var(--flyout)] md:pt-8 md:pb-20"
            >
              <div className="container-nav">
                {/* Утсан дээр apple.com шиг: bar-д зөвхөн X үлдэж, цэсний товчны байрыг эзэлнэ (logo, хайлт,
                    bag нуугдана). Хайлтын талбар доорх тусдаа мөрөнд. md-ээс дээш X байхгүй: bar хэвээр
                    үлдэж, дээрх томруулагч panel-ийг хаана. */}
                <div className="flex h-12 items-center justify-end md:hidden">
                  <button type="button" className={HEADER_CELL} aria-label={t("searchClose")} onClick={close}>
                    <X className="size-[18px]" strokeWidth={1.25} />
                  </button>
                </div>
                <div className="pt-1 md:pt-0">
                  <div className="mx-auto w-full max-w-2xl md:mx-0 md:max-w-none">
                    <SearchBar variant="overlay" onNavigate={close} quickLinks={<QuickLinks onNavigate={close} />} />
                  </div>
                </div>
              </div>
            </div>
          </>,
          document.body,
        )}
    </>
  );
}
