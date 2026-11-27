import { getTranslations } from "next-intl/server";
import { categoryHref } from "@/features/catalog/nav";
import { popular } from "./home-data";
import { TrendingTabs } from "./trending-tabs";

const DEPARTMENTS = ["women", "men", "kids"] as const;

/** Department бүрийн хамгийн эрэлттэй бараа, tab-аар солино. Гурван жагсаалтыг server дээр нэг дор уншина. */
export async function Trending() {
  const [lists, t, d] = await Promise.all([
    Promise.all(DEPARTMENTS.map((department) => popular({ department }, 10))),
    getTranslations("home"),
    getTranslations("home.departments"),
  ]);
  const tabs = DEPARTMENTS.map((department, i) => ({
    value: department,
    label: d(department),
    href: `${categoryHref(department)}?sort=popular`,
    products: lists[i]!,
  })).filter((tab) => tab.products.length > 0);
  if (tabs.length === 0) return null;
  return <TrendingTabs title={t("trending")} seeAll={t("shopAll")} tabs={tabs} />;
}
