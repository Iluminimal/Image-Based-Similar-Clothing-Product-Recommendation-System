"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { browserApi, call } from "@/lib/api/browser";

export const twoFactorKey = ["two-factor"] as const;

/** Ажилтны хоёр шатлалт нэвтрэлтийн төлөв. */
export function useTwoFactorStatus(userId: number | undefined) {
  return useQuery({
    queryKey: [...twoFactorKey, userId],
    queryFn: () => call(browserApi().GET("/api/v1/auth/2fa")),
    enabled: userId !== undefined,
    // Зөвхөн `TwoFactorSetup` "Хадгаллаа" дээр шинэчилнэ. Цонх руу буцах, сүлжээ сэргэх үед өөрөө
    // дахин ачаалбал "идэвхтэй" болж, хараахан хуулж амжаагүй нөөц кодууд дэлгэцээс алга болно.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useSetupTwoFactor() {
  return useMutation({
    mutationFn: (password: string) => call(browserApi().POST("/api/v1/auth/2fa/setup", { body: { password } })),
  });
}

export function useEnableTwoFactor() {
  return useMutation({
    mutationFn: (code: string) => call(browserApi().POST("/api/v1/auth/2fa/enable", { body: { code } })),
  });
}
