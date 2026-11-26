import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import { geistSans } from "@/features/home/fonts";
import { Demo } from "@/features/home/demo";
import { Hero } from "@/features/home/hero";
import { RecentlyViewed } from "@/features/home/recently-viewed";
import { NewArrivals } from "@/features/home/shelves";
import { Trending } from "@/features/home/trending";
import { JsonLdScripts } from "@/features/seo/json-ld-scripts";
import { siteJsonLd } from "@/features/seo/site-json-ld";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("home.meta");
  return {
    title: { absolute: t("title") },
    description: t("description"),
    alternates: { canonical: "/" },
    openGraph: { title: t("title"), description: t("description"), url: "/" },
  };
}

// Хүсэлт бүрт render хийнэ: хуудас каталогийн API-г уншдаг бөгөөд build үед (CI, Docker) API
// байдаггүй. API client-ийн fetch cache (`revalidate`) эдгээрийг хямд байлгана.
export const dynamic = "force-dynamic";

/**
 * Нүүр хуудас (Stripe/Linear хэв, `.home`: цайвар анхдагч, Dark үед хар, Geist): hero (gradient mesh, үг бүр
 * дараалан гарах гарчиг), хуудас дээр ажилладаг зургаар хайлт (live demo), эрэлттэй
 * бараа (tab), шинэ бараа, сүүлд үзсэн. Хөдөлгөөн CSS (`styles/effects.css`); hero-ийн
 * агуулга хэзээ ч нуугддаггүй. Токен: `styles/home.css`.
 */
export default function Home() {
  return (
    <div className={`home ${geistSans.variable}`}>
      <JsonLdScripts nodes={siteJsonLd()} />
      <Hero />
      <Suspense fallback={<div className="container-page -mt-20 min-h-[48rem] md:-mt-28" />}>
        <Demo />
      </Suspense>
      <Suspense fallback={null}>
        <Trending />
      </Suspense>
      <Suspense fallback={null}>
        <NewArrivals />
      </Suspense>
      <RecentlyViewed />
    </div>
  );
}
