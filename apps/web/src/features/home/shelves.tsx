import { getTranslations } from "next-intl/server";
import { Reveal } from "@/components/motion/reveal";
import { ProductRail } from "@/features/catalog/product-rail";
import { newest } from "./home-data";
import { SectionHeading } from "./section-heading";

/** "New arrivals": шинэ нь түрүүнд, нөөцөд байгаа. */
export async function NewArrivals() {
  const [products, t] = await Promise.all([newest({}, 12), getTranslations("home")]);
  if (products.length === 0) return null;
  return (
    <section aria-label={t("newArrivals")} className="container-page defer-render pt-14 pb-4 last:pb-16 md:pt-20 md:last:pb-24">
      <Reveal>
        <SectionHeading title={t("newArrivals")} href="/products?sort=newest" linkLabel={t("shopAll")} />
      </Reveal>
      <ProductRail products={products} label={t("newArrivals")} />
    </section>
  );
}
