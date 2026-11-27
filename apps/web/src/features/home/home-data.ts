import "server-only";
import { listProducts } from "@/features/catalog/api";
import { emptyFilters, type ListingQuery } from "@/features/catalog/filters";
import type { Product } from "@/features/catalog/product";

/**
 * Нөөцтэй бараанууд, шинэ нь эхэнд; `patch`-аар нарийсгана. Хүсэлт амжилтгүй бол "бараа алга" гэж үзнэ:
 * хуудас зурагдсаар байна.
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

/** Нөөцтэй бараанууд, хамгийн эрэлттэй нь эхэнд (`sort=popular`). */
export function popular(patch: Partial<ListingQuery>, count: number): Promise<Product[]> {
  return stocked("popular", patch, count);
}

/**
 * Live demo-ийн жишээ зургууд: каталогийн жинхэнэ гурван бараа (эмэгтэй, эрэгтэй, гутал). Татаж чадаагүй бол
 * жишээгүй.
 */
export async function sampleProducts(): Promise<Product[]> {
  // Жагсаалт бүрээс гурван бараа авна: Unisex бараа эмэгтэй, эрэгтэй хоёр жагсаалтад хоёуланд нь эхэнд орж
  // болдог тул дараагийнх нь хэрэгтэй. Нэг зураг хоёр удаа гарах ёсгүй.
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
