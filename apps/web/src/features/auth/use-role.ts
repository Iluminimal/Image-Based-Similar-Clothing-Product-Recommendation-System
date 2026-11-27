"use client";

import { useAuth } from "./auth-store";
import { isStaffRole } from "./roles";

/** Админ эсвэл агуулахын ажилтан бол back-office-ийн хэрэглэгч: storefront дээр сагс, захиалга ашиглахгүй. */
export function useIsStaff(): boolean {
  return useAuth((state) => isStaffRole(state.user?.role));
}

/** Админ эсэх (хэрэглэгч, сэтгэгдэл, статистик харах, захиалга цуцлах, төлбөр буцаах эрхтэй). */
export function useIsAdmin(): boolean {
  return useAuth((state) => state.user?.role === "admin");
}

/** Агуулахын ажилтан эсэх (бараа, нөөц өөрчлөх, захиалга илгээх, хүргэх эрхтэй). */
export function useIsWarehouse(): boolean {
  return useAuth((state) => state.user?.role === "warehouse");
}
