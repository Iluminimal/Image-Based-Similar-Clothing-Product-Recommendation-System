import { ArrowRight, ScanSearch } from "lucide-react";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import type { CSSProperties } from "react";
import { SplitWords } from "@/components/motion/split-words";
import { Button } from "@/components/ui/button";

/**
 * Эхний хэсэг (Stripe/Linear хэв): ард нь зөөлөн gradient mesh, голд нь шошго, том гарчиг, нэг мөр тайлбар, хоёр
 * товч. Зураг байхгүй: доорх live demo нь харагдах гол зүйл. Гарчиг хэзээ ч нуугддаггүй (LCP нь текст).
 */
export async function Hero() {
  const t = await getTranslations("home.hero");
  return (
    <section aria-label={t("label")} className="relative isolate overflow-clip">
      <div aria-hidden className="home-mesh absolute inset-x-0 top-0 -z-10 h-[44rem]">
        <i />
        <i />
        <i />
        <i />
      </div>
      <div aria-hidden className="home-grid absolute inset-x-0 top-0 -z-10 h-[32rem]" />
      <div className="container-page flex flex-col items-center pt-16 pb-28 text-center md:pt-24 md:pb-36">
        <p style={{ "--d": "0ms" } as CSSProperties} className="home-pill-badge hero-rise">
          <ScanSearch aria-hidden className="size-3.5" /> {t("label")}
        </p>
        <h1 className="home-title mt-6 max-w-4xl">
          <SplitWords>{t.rich("heading", { g: (chunks) => <span className="text-gradient">{chunks}</span> })}</SplitWords>
        </h1>
        <p style={{ "--d": "280ms" } as CSSProperties} className="text-muted-foreground hero-rise mt-5 max-w-xl text-lg">
          {t("sub")}
        </p>
        <div style={{ "--d": "380ms" } as CSSProperties} className="hero-rise mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button asChild size="xl">
            <a href="#demo">
              {t("try")} <ArrowRight aria-hidden />
            </a>
          </Button>
          <Button asChild variant="bordered" size="xl">
            <Link href="/products?sort=newest">{t("newArrivals")}</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
