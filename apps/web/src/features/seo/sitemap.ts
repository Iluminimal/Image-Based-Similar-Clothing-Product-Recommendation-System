import type { MetadataRoute } from "next";
import { categoryPaths, type CatalogNav } from "@/features/catalog/nav";
import { productPath } from "@/features/catalog/product";
import { absoluteUrl } from "@/lib/site";

/** Нэг sitemap файлд орох барааны тоо. Протокол 50,000 URL хүртэл зөвшөөрдөг ч жижиг файл хурдан үүснэ. */
export const SITEMAP_CHUNK = 10_000;

/** `total` бүтээгдэхүүнтэй catalogue-ийн sitemap файлын id-ууд (хамгийн багадаа нэг). */
export function sitemapIds(total: number): { id: number }[] {
  const files = Math.max(1, Math.ceil(total / SITEMAP_CHUNK));
  return Array.from({ length: files }, (_, id) => ({ id }));
}

/** Бараа, ангиллаас бусад хуудсууд: нүүр, жагсаалт, зургаар хайх. */
export function staticEntries(): MetadataRoute.Sitemap {
  return [
    { url: absoluteUrl("/"), changeFrequency: "daily", priority: 1 },
    { url: absoluteUrl("/products"), changeFrequency: "daily", priority: 0.8 },
    { url: absoluteUrl("/search"), changeFrequency: "monthly", priority: 0.5 },
  ];
}

/**
 * Бүх department, ангиллын хуудас (/c/men, /c/men/apparel/topwear, ...). Дээд түвшний хуудсанд өндөр rank
 * өгнө.
 */
export function categoryEntries(nav: CatalogNav): MetadataRoute.Sitemap {
  return categoryPaths(nav).map((path) => ({
    url: absoluteUrl(path),
    changeFrequency: "daily",
    priority: Math.max(0.4, 0.8 - 0.1 * (path.split("/").length - 3)),
  }));
}

export function productEntries(items: { id: number; slug: string; updated_at: string }[]): MetadataRoute.Sitemap {
  return items.map((item) => ({
    url: absoluteUrl(productPath(item)),
    lastModified: new Date(item.updated_at),
    changeFrequency: "weekly",
    priority: 0.6,
  }));
}

/** Sitemap файл бүр хаана байх (`/sitemap/<id>.xml`). */
export const sitemapUrl = (id: number) => absoluteUrl(`/sitemap/${id}.xml`);

/**
 * Хайлтын системд зориулсан дүрэм. Account, cart, checkout, админ хуудсууд хувийн. Текстээр хайсан, цааш гүн
 * орсон хуудсууд `noindex` бөгөөд crawler тэнд цаг зарцуулах хэрэггүй (бараанууд sitemap-д бий).
 */
export function robotsFor(ids: number[]): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/account",
        "/admin",
        "/cart",
        "/checkout",
        "/login",
        "/register",
        "/api/",
        "/*?*q=",
        "/*?*page=",
      ],
    },
    sitemap: ids.map(sitemapUrl),
  };
}
