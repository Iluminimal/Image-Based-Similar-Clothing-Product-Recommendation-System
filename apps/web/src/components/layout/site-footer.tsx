import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { ShopperOnly } from "@/features/auth/shopper-only";
import { categoryHref } from "@/features/catalog/nav";
import { getVocab } from "@/i18n/server";

const LINK =
  "text-foreground/80 hover:text-foreground focus-visible:ring-ring/50 inline-block rounded-sm py-1 transition-colors outline-none hover:underline focus-visible:ring-3";

/**
 * Apple-ийн маягийн footer: цайвар саарал дэвсгэр, 12px үсэг, багана бүрд жижиг тод гарчигтай богино
 * холбоосууд, "more ways to shop" мөр, copyright. Хэсгүүдийг 1px нарийн зураас тусгаарлана. Утсан дээр
 * баганууд хураагдахгүй: зэрэгцсэн хоёр баганад холбоос бүр нэг товшилтын зайд байна.
 */
export async function SiteFooter() {
  const [t, vocab] = await Promise.all([getTranslations("layout.footer"), getVocab()]);
  const columns = [
    {
      title: t("shop"),
      links: [
        { href: categoryHref("women"), label: vocab.department("Women") },
        { href: categoryHref("men"), label: vocab.department("Men") },
        { href: categoryHref("kids"), label: vocab.department("Kids") },
        { href: "/products?sort=newest", label: t("newArrivals") },
      ],
    },
    {
      title: t("discover"),
      links: [
        { href: "/search", label: t("searchByPhoto") },
        { href: "/products", label: t("allProducts") },
      ],
    },
    {
      title: t("account"),
      links: [
        { href: "/account/profile", label: t("profile"), private: true },
        { href: "/account/orders", label: t("orders"), private: true, shopperOnly: true },
        { href: "/account/wishlist", label: t("wishlist"), private: true, shopperOnly: true },
        { href: "/cart", label: t("bag"), shopperOnly: true },
      ],
    },
  ];
  return (
    <footer className="bg-secondary text-muted-foreground type-fine mt-16">
      <div className="container-nav pt-4 pb-5 md:pt-5">
        <div className="border-border grid grid-cols-2 gap-x-6 gap-y-8 border-b py-6 md:grid-cols-3 md:py-8">
          {columns.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <p className="text-foreground mb-2.5 font-semibold">{column.title}</p>
              <ul className="space-y-0.5">
                {column.links.map((link) => {
                  const item = (
                    <li key={link.href}>
                      {/* Нэвтрээгүй зочин account хуудас руу орвол login руу redirect хийгддэг. Урьдчилан
                          татвал (prefetch) тэр redirect cache-д үлдэж, нэвтэрсний дараа ч /login руу буцаана. */}
                      <Link href={link.href} prefetch={"private" in link ? false : undefined} className={LINK}>
                        {link.label}
                      </Link>
                    </li>
                  );
                  return "shopperOnly" in link ? <ShopperOnly key={link.href}>{item}</ShopperOnly> : item;
                })}
              </ul>
            </nav>
          ))}
        </div>
        <p className="border-border border-b py-3">
          {t.rich("moreWays", {
            photo: (chunks) => (
              <Link href="/search" className="text-brand underline underline-offset-2">
                {chunks}
              </Link>
            ),
            all: (chunks) => (
              <Link href="/products" className="text-brand underline underline-offset-2">
                {chunks}
              </Link>
            ),
          })}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 pt-3">
          <p>{t("copyright", { year: new Date().getFullYear() })}</p>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </div>
      </div>
    </footer>
  );
}
