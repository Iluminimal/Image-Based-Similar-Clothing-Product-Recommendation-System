/** TanStack Query-ийн нийтлэг тохиргоо. */

import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: false },
      // Анхдагчаар сүлжээгүй үед өөрчлөлт чимээгүй хүлээж, сүлжээ орохоор өөрөө илгээгддэг: товч
      // тайлбаргүй эргэлдэж, хүн мартсан үйлдэл хожим биелнэ. "always" бол шууд оролдож, алдааг
      // хэлнэ; дахин хийх эсэхийг хүн шийднэ.
      mutations: { networkMode: "always" },
    },
  });
}
