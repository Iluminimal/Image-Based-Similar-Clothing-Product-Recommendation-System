import { browserApi, call } from "@/lib/api/browser";
import type { components } from "@/lib/api/client";

export type Order = components["schemas"]["OrderOut"];
export type OrderSummary = components["schemas"]["OrderSummary"];
export type OrderPage = components["schemas"]["OrderPage"];
export type OrderRequest = components["schemas"]["OrderRequestOut"];
export type OrderRequestInput = components["schemas"]["OrderRequestCreate"];
export type RequestKind = OrderRequest["kind"];
export type RequestReason = OrderRequest["reason"];

/** Төрөл бүрийн хүсэлтэд сонгож болох шалтгаанууд (API-тай ижил). */
export const REQUEST_REASONS = {
  cancel: ["changed_mind", "wrong_order", "too_slow", "other"],
  return: ["wrong_size", "not_as_described", "defective", "wrong_item", "changed_mind", "other"],
} as const satisfies Record<RequestKind, readonly RequestReason[]>;

export const createOrderRequest = (number: string, body: OrderRequestInput) =>
  call(browserApi().POST("/api/v1/orders/{number}/requests", { params: { path: { number } }, body }));

export const withdrawOrderRequest = (number: string, requestId: number) =>
  call(
    browserApi().POST("/api/v1/orders/{number}/requests/{request_id}/withdraw", {
      params: { path: { number, request_id: requestId } },
    }),
  );

export const fetchOrders = (page: number) =>
  call(browserApi().GET("/api/v1/orders", { params: { query: { page, page_size: 10 } } }));

/** Төлбөр хүлээж буй захиалгыг цуцална: нөөц буцаж, нэхэмжлэх хаагдана. */
export const cancelOrder = (number: string) =>
  call(browserApi().POST("/api/v1/orders/{number}/cancel", { params: { path: { number } } }));

export const fetchOrder = (number: string) =>
  call(browserApi().GET("/api/v1/orders/{number}", { params: { path: { number } } }));

/** Өмнөх захиалгын бараануудыг сагсанд буцаана (нөөцөөр хязгаарлагдсан): нэмэгдээгүйг шалтгаантай нь буцаана. */
export const reorderOrder = (number: string) =>
  call(browserApi().POST("/api/v1/orders/{number}/reorder", { params: { path: { number } } }));
