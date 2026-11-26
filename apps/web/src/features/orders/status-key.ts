import type { Order } from "./orders-api";

export type StatusKey = Order["status"] | "ready_for_pickup" | "collected";

/**
 * Төлвийн харуулах нэр (`orders.status.*`). Дэлгүүрээс авах захиалгад ижил төлөв өөр утгатай:
 * `shipped` нь "авахад бэлэн", `delivered` нь "авсан".
 */
export function statusKey(status: Order["status"], shippingMethod?: string): StatusKey {
  if (shippingMethod === "pickup") {
    if (status === "shipped") return "ready_for_pickup";
    if (status === "delivered") return "collected";
  }
  return status;
}
