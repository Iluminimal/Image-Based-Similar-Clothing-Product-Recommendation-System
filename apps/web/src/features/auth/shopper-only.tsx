"use client";

import type { ReactNode } from "react";
import { useIsStaff } from "./use-role";

/** Худалдан авагчид л хамаатай зүйл: админ, агуулахын ажилтанд харагдахгүй. Server component дотроос ашиглаж болно. */
export function ShopperOnly({ children }: { children: ReactNode }) {
  return useIsStaff() ? null : children;
}
