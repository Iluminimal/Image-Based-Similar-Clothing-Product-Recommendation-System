import "server-only";
import { listProducts } from "@/features/catalog/api";
import { emptyFilters, type ListingQuery } from "@/features/catalog/filters";
import type { Product } from "@/features/catalog/product";

/**
 * Нөөцөд байгаа бүтээгдэхүүн, шинэ нь түрүүнд, `patch`-аар нарийсгана. Амжилтгүй хүсэлт нь
 * "бүтээгдэхүүнгүй": хуудас рендерлэгдсээр байна.
 */
async function stocked(sort: ListingQuery["sort"], patch: Partial<ListingQuery>, count: number): Promise<Product[]> {
  try {
    const { items } = await listProducts({ ...emptyFilters(), page: 1, in_stock: true, sort, ...patch }, count);
    return items;
  } catch {
    return [];
  }
}

export function newest(patch: Partial<ListingQuery>, count: number): Promise<Product[]> {
  return stocked("newest", patch, count);
}

/** Хамгийн эрэлттэй нь түрүүнд (`sort=popular`), нөөцөд байгаа. */
export function popular(patch: Partial<ListingQuery>, count: number): Promise<Product[]> {
  return stocked("popular", patch, count);
}

/** Live demo-ийн жишээ зургууд: бодит каталогийн гурван хувцас (эмэгтэй, эрэгтэй, гутал). Бүтэлгүйтвэл жишээгүй. */
export async function sampleProducts(): Promise<Product[]> {
  // Жагсаалт бүрээс гурвыг авна: Unisex бараа эмэгтэй, эрэгтэй хоёрт зэрэг тэргүүлж болдог тул
  // дараагийнх нь хэрэгтэй. Нэг зураг хоёр удаа гарах ёсгүй.
  const found = await Promise.all([
    popular({ department: "women", category: "apparel" }, 3),
    popular({ department: "men", category: "apparel" }, 3),
    popular({ category: "footwear" }, 3),
  ]);
  const picked = new Map<number, Product>();
  for (const items of found) {
    const next = items.find((product) => !picked.has(product.id));
    if (next) picked.set(next.id, next);
  }
  return [...picked.values()];
}
