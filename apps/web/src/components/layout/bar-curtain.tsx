"use client";

import { announceFlyout } from "./bar-flyout";

/**
 * apple.com-ийн curtain: bar-ын доор flyout нээлттэй үед (`<html>` дээр `data-bar-panel` байвал CSS харуулна)
 * хуудасны үлдсэн хэсгийг бүрхэж бүдгэрүүлнэ. Дарахад flyout хаагдана. Header дотор тавиагүй: header-ийн
 * backdrop blur доторх `fixed` бүх элементийг өөртөө уяж орхидог.
 */
export function BarCurtain() {
  return <div aria-hidden className="bar-curtain" onClick={() => announceFlyout(null)} />;
}
