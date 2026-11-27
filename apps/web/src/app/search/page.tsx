import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { getCatalogFilters } from "@/features/catalog/api";
import { SearchView } from "@/features/search/search-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("search.meta");
  return {
    title: t("title"),
    description: t("description"),
    alternates: { canonical: "/search" },
    openGraph: { title: t("title"), url: "/search" },
  };
}

// Хүсэлт бүрд render хийнэ: хуудас каталогийн API-аас уншдаг, харин build хийх үед (CI, Docker) API байхгүй.
// API client-ийн fetch cache (`revalidate`) ачааллыг багасгана.
export const dynamic = "force-dynamic";

export default async function SearchPage() {
  const options = await getCatalogFilters();
  return <SearchView options={options} />;
}
