import { getTranslations } from "next-intl/server";
import imageLoader from "@/lib/image-loader";
import { LiveSearch } from "./live-search";
import { sampleProducts } from "./home-data";

/**
 * Live demo-ийн server талын хэсэг: каталогийн жинхэнэ жишээ зургуудыг уншиж client component-д дамжуулна.
 * Зургийн хаяг бусад зурагтай адил энэ сайтын `/media` route-оор явна (`lib/image-loader.ts`): CSP, нэг
 * origin.
 */
export async function Demo() {
  const [samples, t] = await Promise.all([sampleProducts(), getTranslations("home.demo")]);
  return (
    <section id="demo" aria-label={t("label")} className="container-page relative z-10 -mt-20 scroll-mt-24 md:-mt-28">
      <LiveSearch samples={samples.map((product) => ({ id: product.id, name: product.name, src: imageLoader({ src: product.image.thumb_800, width: 800 }) }))} />
    </section>
  );
}
