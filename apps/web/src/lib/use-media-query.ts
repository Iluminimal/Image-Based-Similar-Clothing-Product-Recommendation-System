import { useSyncExternalStore } from "react";

/** Media query таарч байгаа эсэх (өөрчлөгдөхөд шинэчлэгдэнэ). Server болон hydration үед false. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
