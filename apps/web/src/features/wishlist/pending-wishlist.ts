import type { Product } from "@/features/catalog/product";

const KEY = "angel:pending-wishlist";

/**
 * Зочин зүрх дарсан барааг түр санаад, нэвтрэх хуудас руу явна. Нэвтэрсний дараа автоматаар хадгална
 * (`PendingWishlistReplay`). sessionStorage ашигладаг тул зөвхөн энэ tab-д, хаавал алга болно. Хадгалах
 * боломжгүй (private горим) бол чимээгүй алгасна.
 */
export function rememberPendingWishlist(product: Product): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(product));
  } catch {
    // хадгалж чадахгүй бол хэрэглэгч нэвтэрсний дараа дахин дарна
  }
}

/** Хадгалсан барааг нэг удаа авч, устгана. */
export function takePendingWishlist(): Product | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(KEY);
    const product = JSON.parse(raw) as Product;
    return typeof product?.id === "number" ? product : null;
  } catch {
    return null;
  }
}
