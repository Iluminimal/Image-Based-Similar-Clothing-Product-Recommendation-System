import { useTranslations } from "next-intl";
import { StatusDot, type Tone } from "@/components/admin/status-dot";
import type { Order } from "@/features/orders/orders-api";
import { statusKey } from "@/features/orders/status-key";

/** Захиалгын төлөв бүрийн өнгө: "илгээх" (төлөгдсөн) нь админы үйлдэл хүлээж буй тул анхаарал татна. */
export const ORDER_TONE: Record<Order["status"], Tone> = {
  pending: "neutral",
  paid: "warning",
  shipped: "info",
  delivered: "success",
  cancelled: "danger",
  refunded: "neutral",
};

export function OrderStatusDot({ status, shippingMethod }: { status: Order["status"]; shippingMethod?: string }) {
  const t = useTranslations("orders.status");
  return <StatusDot tone={ORDER_TONE[status]}>{t(statusKey(status, shippingMethod))}</StatusDot>;
}
