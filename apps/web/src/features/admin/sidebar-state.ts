import { useSyncExternalStore } from "react";

const KEY = "angel.admin.sidebar-collapsed";
const listeners = new Set<() => void>();
// Storage хаалттай (private mode г.м.) үед сонголт энэ tab-ын санах ойд үлдэнэ.
let fallback = false;

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return fallback;
  }
}

function write(collapsed: boolean) {
  fallback = collapsed;
  try {
    window.localStorage.setItem(KEY, collapsed ? "1" : "0");
  } catch {}
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** Ажилтны sidebar хумигдсан эсэх, энэ browser-т хадгалагдана. Сервер дээр үргэлж дэлгэсэн. */
export function useSidebarCollapsed() {
  const collapsed = useSyncExternalStore(subscribe, read, () => false);
  return [collapsed, () => write(!collapsed)] as const;
}
