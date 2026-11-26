/**
 * Сагсны самбарын дэлгэцийн төлөв: нээлттэй эсэх, дөнгөж нэмсэн ба хассан мөр. Сагсны өгөгдөл энд
 * биш, `use-cart.ts`-д.
 */

import { create } from "zustand";
import { announceFlyout } from "@/components/layout/bar-flyout";

/** Дөнгөж нэмсэн мөр (Bag-д тодруулж харуулна), бүтээгдэхүүн ба хэмжээгээр нь танина. */
export type AddedLine = { productId: number; size: string };

/** Cart-аас хамгийн сүүлд хассан мөр, буцааж тавихад зориулав. */
export type RemovedLine = { productId: number; size: string; quantity: number; name: string };

type CartUi = {
  open: boolean;
  setOpen: (open: boolean) => void;
  added: AddedLine | null;
  setAdded: (line: AddedLine | null) => void;
  removed: RemovedLine | null;
  setRemoved: (line: RemovedLine | null) => void;
};

/** Bag самбар нээлттэй эсэх, ингэснээр "Add to cart" хаанаас ч түүнийг харуулж чадна. */
export const useBagPanel = create<CartUi>((set) => ({
  open: false,
  setOpen: (open) => {
    // Bar-ын доор нээлттэй байгаа search эсвэл department цэс Bag-д зам тавьж өгнө.
    if (open) announceFlyout("bag");
    set(open ? { open } : { open, added: null });
  },
  added: null,
  setAdded: (added) => set({ added }),
  removed: null,
  setRemoved: (removed) => set({ removed }),
}));
