import { useEffect } from "react";

/** Md-ээс дээш bar-ын доор нээгддэг хуудсууд: ангиллын цэс, хайлт, Bag. */
export type Flyout = "menu" | "search" | "bag";

const EVENT = "bar-flyout";

/**
 * `flyout` дөнгөж нээгдсэнийг бусдад мэдэгдэнэ. Нээлттэй бусад flyout хаагдана (`useCloseOnOtherFlyout`-ыг
 * үзнэ үү).
 */
export function announceFlyout(flyout: Flyout | null) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(EVENT, { detail: flyout }));
}

/**
 * apple.com шиг нэг үед нэг л flyout: хайлт нээхэд Bag хаагдаж, department дээр hover хийхэд хайлт солигдоно
 * гэх мэт. Flyout бүр өөрийн state-тэй, энэ hook-ийг өөрийн нэрээр дууддаг.
 */
export function useCloseOnOtherFlyout(self: Flyout, close: () => void) {
  useEffect(() => {
    function onOther(event: Event) {
      if ((event as CustomEvent<Flyout | null>).detail !== self) close();
    }
    window.addEventListener(EVENT, onOther);
    return () => window.removeEventListener(EVENT, onOther);
  }, [self, close]);
}
