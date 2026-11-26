import type { AdminOrder, AdminOrderRequest } from "./admin-api";

const OPEN = ["requested", "approved", "received"];

/** Шийдэгдэж дуусаагүй хүсэлт (захиалгад нэгээс илүүгүй). */
export const openRequestOf = (order: AdminOrder): AdminOrderRequest | undefined =>
  order.requests.find((request) => OPEN.includes(request.status));
