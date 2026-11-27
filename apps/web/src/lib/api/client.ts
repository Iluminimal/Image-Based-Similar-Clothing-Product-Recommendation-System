/**
 * API client-ийн суурь. Төрлүүд (`schema.d.ts`) нь API-ийн OpenAPI schema-гаас `make api-types`-аар
 * үүсдэг тул гараар засахгүй.
 */

import createClient from "openapi-fetch";
import { env } from "@/lib/env";
import type { paths } from "./schema";

// Server component-ууд API руу дотоод сүлжээний хаягаар (docker) хандаж болно. Browser үргэлж нийтийн хаягийг
// ашиглана. `API_INTERNAL_URL` client-д хэзээ ч харагдахгүй.
export function apiBaseUrl(): string {
  if (typeof window === "undefined" && process.env.API_INTERNAL_URL) {
    return process.env.API_INTERNAL_URL;
  }
  return env.NEXT_PUBLIC_API_URL;
}

type Revalidate = number | false;

/**
 * Үүсгэсэн OpenAPI `paths`-д тохирсон төрөлтэй client. `revalidate` бол Next.js-ийн fetch cache хадгалах
 * секунд (зөвхөн server дээр, browser үүнийг тооцохгүй). Давтагдсан параметрийг API-ийн хүлээдгээр
 * `gender=Men&gender=Unisex` гэж бичнэ.
 */
export function createApiClient(revalidate?: Revalidate) {
  return createClient<paths>({
    baseUrl: apiBaseUrl(),
    fetch: (request) =>
      fetch(request, revalidate === undefined ? undefined : { next: { revalidate } }),
  });
}

export type { components } from "./schema";
