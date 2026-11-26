import { getTranslations } from "next-intl/server";
import imageLoader from "@/lib/image-loader";
import { LiveSearch } from "./live-search";
import { sampleProducts } from "./home-data";

/**
 * Live demo-ийн сервер талын хэсэг: бодит каталогийн жишээ зургуудыг уншиж client component-д өгнө. Зургийн хаяг нь
 * бусад зургийнх шиг энэ сайтын өөрийн `/media` route руу шилждэг (`lib/image-loader.ts`): CSP, нэг origin.
 */
export async function Demo() {
  const [samples, t] = await Promise.all([sampleProducts(), getTranslations("home.demo")]);
  return (
    <section id="demo" aria-label={t("label")} className="container-page relative z-10 -mt-20 scroll-mt-24 md:-mt-28">
      <LiveSearch samples={samples.map((product) => ({ id: product.id, name: product.name, src: imageLoader({ src: product.image.thumb_800, width: 800 }) }))} />
    </section>
  );
}
