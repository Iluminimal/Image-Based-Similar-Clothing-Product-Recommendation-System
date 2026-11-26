"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme/theme-provider";
import dynamic from "next/dynamic";
import { AuthBootstrap } from "@/features/auth/auth-bootstrap";
import { PendingWishlistReplay } from "@/features/wishlist/pending-wishlist-replay";
import { createQueryClient } from "@/lib/query-client";
import { useState, type ReactNode } from "react";

// Toast ховор бөгөөд үйлдлийн дараа гарна, анхны paint-д хэзээ ч байхгүй: renderer-ийг түүний дараа
// ачаална.
const Toaster = dynamic(() => import("@/components/ui/sonner").then((m) => m.Toaster), { ssr: false });

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthBootstrap />
        <PendingWishlistReplay />
        {children}
        <Toaster position="bottom-center" />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
