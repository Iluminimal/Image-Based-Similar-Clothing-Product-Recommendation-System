/** Захиалах хуудасны API дуудлагууд. */

import { browserApi, call } from "@/lib/api/browser";
import type { components } from "@/lib/api/client";

export type ShippingMethods = components["schemas"]["ShippingMethodList"];
export type ShippingMethodId = components["schemas"]["ShippingMethodOut"]["id"];
export type ShippingZone = "ub" | "rural";
export type Charge = components["schemas"]["ChargeOut"];
export type QPayCheckout = components["schemas"]["QPayCheckoutOut"];

/** Хүргэлтийн төрөл, үнэ: Улаанбаатар (`ub`) эсвэл орон нутаг (`rural`). */
export const fetchShippingMethods = (zone: ShippingZone = "ub") =>
  call(browserApi().GET("/api/v1/checkout/shipping-methods", { params: { query: { zone } } }));

/** Захиалга үүсэхээс өмнө checkout ямар аргаар төлбөр авахыг асууна (QPay эсвэл demo). */
export const fetchPaymentMethod = () => call(browserApi().GET("/api/v1/checkout/payment-method"));

/** Сагсны барааг нөөцөлж, захиалга үүсгэнэ. Ижил key үргэлж ижил захиалгыг буцаана. */
export const createCheckout = (
  body: { address_id: number; shipping_method: ShippingMethodId; contact_email?: string; expected_total_cents: number },
  key: string,
) =>
  call(browserApi().POST("/api/v1/checkout", { body, params: { header: { "idempotency-key": key } } }));

/**
 * Demo төлбөр: API-ийн offline gateway-ээр захиалгыг төлөгдсөн гэж тэмдэглэнэ. Картын өгөгдөл
 * илгээхгүй.
 */
export const payDemoOrder = (number: string) =>
  call(
    browserApi().POST("/api/v1/checkout/orders/{number}/simulate-payment", {
      params: { path: { number } },
    }),
  );

/**
 * QPay: худалдан авагч "Төлбөрөө шалгах" дарсан эсвэл хуудас руу буцаж ирсэн үед дуудна. API QPay-ээс асууж,
 * төлөгдсөн бол захиалгыг төлөгдсөн болгоод буцаана.
 */
export const checkPayment = (number: string) =>
  call(
    browserApi().POST("/api/v1/checkout/orders/{number}/check-payment", {
      params: { path: { number } },
    }),
  );
