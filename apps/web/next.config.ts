import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { staticSecurityHeaders } from "./src/lib/security-headers";

// URL-д хэлний угтвар (/mn, /en) байхгүй. Хэлийг cookie-гоор, эхний удаа Accept-Language-аар тогтооно
// (`src/i18n/request.ts`).
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Browser API-г энэ сайтаар дамжуулан (нэг origin) дууддаг. Тиймээс httpOnly refresh cookie сайтын өөрийн
// cookie болно. Server талын код API руу API_INTERNAL_URL-ээр шууд хандана.
const apiOrigin =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Docker image (apps/web/Dockerfile) `NEXT_OUTPUT=standalone`-ээр хэрэгтэй бүхнээ агуулсан server
  // (`server.js`) үүсгэнэ. `next start` ашигладаг локал build (e2e, Lighthouse) үүнийг ашиглахгүй.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // `X-Powered-By: Next.js` header зөвхөн халдагчид мэдээлэл өгөх тул унтраана.
  poweredByHeader: false,
  images: {
    loader: "custom",
    loaderFile: "./src/lib/image-loader.ts",
  },
  async headers() {
    // CSP-г (хүсэлт бүрт nonce хэрэгтэй) `src/proxy.ts` тавина; үлдсэн нь тогтмол.
    return [{ source: "/:path*", headers: staticSecurityHeaders({ production: process.env.NODE_ENV === "production" }) }];
  },
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` },
      // Барааны зургийг ч энэ origin-оос өгнө. Ингэснээр browser API руу хоёр дахь холболт нээхгүй, хуудас
      // ирсэн холболтыг ашиглана.
      { source: "/media/:path*", destination: `${apiOrigin}/media/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
