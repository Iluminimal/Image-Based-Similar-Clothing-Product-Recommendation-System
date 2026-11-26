import { Heart, MapPin, Package, UserRound } from "lucide-react";
import { isStaffRole } from "./roles";

const ACCOUNT_LINKS = [
  { href: "/account/profile", key: "profile", icon: UserRound, shopperOnly: false },
  { href: "/account/orders", key: "orders", icon: Package, shopperOnly: true },
  { href: "/account/wishlist", key: "wishlist", icon: Heart, shopperOnly: true },
  { href: "/account/addresses", key: "addresses", icon: MapPin, shopperOnly: true },
] as const;

/** Тухайн role-ийн бүртгэлийн цэс. Ажилтан худалдан авалт хийдэггүй тул зөвхөн профайлаа харна. */
export function accountLinks(role: string | undefined) {
  const staff = isStaffRole(role);
  return ACCOUNT_LINKS.filter((link) => !(staff && link.shopperOnly));
}
