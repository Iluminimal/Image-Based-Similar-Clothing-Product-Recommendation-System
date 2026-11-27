import type { ShippingMethodId, ShippingMethods } from "./checkout-api";

/**
 * Хуудсан дээр шууд харуулах нийт дүнд зориулж хүргэлтийн үнийг тооцно. Жинхэнэ дүнг захиалга үүсгэхэд сервер
 * тогтоодог; энэ нь түүний дүрмийг давтана (энгийн хүргэлт босгоос дээш үнэгүй, дэлгүүрээс авах нь үргэлж
 * үнэгүй).
 */
export function shippingCostFor(methods: ShippingMethods, id: ShippingMethodId, subtotalCents: number): number {
  const method = methods.items.find((m) => m.id === id);
  if (!method) return 0;
  if (id === "standard" && subtotalCents >= methods.free_shipping_threshold_cents) return 0;
  return method.price_cents;
}
