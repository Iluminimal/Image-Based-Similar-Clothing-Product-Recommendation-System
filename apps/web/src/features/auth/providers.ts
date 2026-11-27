import "server-only";
import { cache } from "react";
import { createApiClient } from "@/lib/api/client";

/**
 * API нэвтрэх ямар нэмэлт арга санал болгодгийг асууна. Алдаа гарвал тийм арга "байхгүй" гэж үзнэ: API-аас
 * асууж чадаагүй ч login хуудас нууц үгийн form-ыг харуулах ёстой.
 */
export const getAuthProviders = cache(async (): Promise<{ google: boolean }> => {
  try {
    const { data, error } = await createApiClient(60).GET("/api/v1/auth/providers");
    if (error) console.error("auth providers lookup failed; hiding Google sign-in", error);
    return { google: data?.google === true };
  } catch (error) {
    // API унасан үед Google товч яагаад алга болсныг server log-оос харж болохоор бичнэ.
    console.error("auth providers lookup failed; hiding Google sign-in", error);
    return { google: false };
  }
});
