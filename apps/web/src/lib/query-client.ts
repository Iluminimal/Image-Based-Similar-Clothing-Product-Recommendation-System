/** TanStack Query-ийн нийтлэг тохиргоо. */

import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: false },
      // Анхдагчаар сүлжээгүй үед өөрчлөх үйлдэл чимээгүй хүлээж, сүлжээ ирмэгц өөрөө явдаг. Тэгвэл товч
      // тайлбаргүй эргэлдэж, хүн мартсан үйлдэл нь хожим биелнэ. "always" бол шууд оролдож, алдааг нь хэлнэ:
      // дахин оролдох эсэхийг хүн өөрөө шийднэ.
      mutations: { networkMode: "always" },
    },
  });
}
