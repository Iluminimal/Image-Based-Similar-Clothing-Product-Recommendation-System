"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-store";
import { browserApi, call } from "@/lib/api/browser";
import { queryKeys } from "@/lib/query-keys";

type Password = { current_password?: string; reauth_code?: string };

/** Нууц үггүй account: эмзэг үйлдлийг батлах код илгээхийг хүснэ. */
export function useRequestReauth() {
  return useMutation({ mutationFn: () => call(browserApi().POST("/api/v1/auth/reauth/request")) });
}

/**
 * Утас, имэйл: код авах, баталгаажуулах, устгах. Амжилт бүрт хадгалсан хэрэглэгчийн мэдээлэл
 * шинэчлэгдэнэ.
 */
export function useRequestPhone() {
  return useMutation({
    mutationFn: (body: Password & { phone: string }) => call(browserApi().POST("/api/v1/auth/phone/request", { body })),
  });
}

export function useConfirmPhone() {
  return useMutation({
    mutationFn: (body: { phone: string; code: string }) => call(browserApi().POST("/api/v1/auth/phone/confirm", { body })),
    onSuccess: (user) => useAuth.setState({ user }),
  });
}

export function useRemovePhone() {
  return useMutation({
    mutationFn: (body: Password) => call(browserApi().DELETE("/api/v1/auth/phone", { body })),
    onSuccess: (user) => useAuth.setState({ user }),
  });
}

export function useRequestEmail() {
  return useMutation({
    mutationFn: (body: Password & { email: string }) => call(browserApi().POST("/api/v1/auth/email/request", { body })),
  });
}

export function useConfirmEmail() {
  return useMutation({
    mutationFn: (body: { email: string; code: string }) => call(browserApi().POST("/api/v1/auth/email/confirm", { body })),
    onSuccess: (user) => useAuth.setState({ user }),
  });
}

export function useRemoveEmail() {
  return useMutation({
    mutationFn: (body: Password) => call(browserApi().DELETE("/api/v1/auth/email", { body })),
    onSuccess: (user) => useAuth.setState({ user }),
  });
}

/** Бүртгэлд байгаа хаягийг баталгаажуулна. */
export function useRequestEmailVerification() {
  return useMutation({ mutationFn: () => call(browserApi().POST("/api/v1/auth/email/verify/request")) });
}

export function useConfirmEmailVerification() {
  return useMutation({
    mutationFn: (code: string) => call(browserApi().POST("/api/v1/auth/email/verify/confirm", { body: { code } })),
    onSuccess: (user) => useAuth.setState({ user }),
  });
}

// --- төхөөрөмжүүд --- ------------------------------------------------------------------------

export function useSessions(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.sessions,
    queryFn: () => call(browserApi().GET("/api/v1/auth/sessions")),
    enabled,
  });
}

/** Бүртгэлийн сүүлийн аюулгүй байдлын үйл явдлууд (нэвтрэлт, нууц үг солих, төхөөрөмж цуцлах). */
export function useSecurityEvents(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.securityEvents,
    queryFn: () => call(browserApi().GET("/api/v1/auth/security-events")),
    enabled,
    // Профайл руу орох бүрд шинээр татна: хэн нэгэн нэвтэрсэн бол эзэн нь даруй харах ёстой.
    staleTime: 0,
  });
}

/** Нэг төхөөрөмжийг гаргана. Яг энэ browser-ыг гаргавал санах ойн session-ыг бас цэвэрлэнэ. */
export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, current }: { id: string; current: boolean }) => {
      await call(browserApi().DELETE("/api/v1/auth/sessions/{session_id}", { params: { path: { session_id: id } } }));
      return current;
    },
    onSuccess: async (wasCurrent) => {
      if (wasCurrent) useAuth.getState().clear();
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });
}

export function useRevokeOtherSessions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => call(browserApi().POST("/api/v1/auth/sessions/revoke-others")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.sessions }),
  });
}
