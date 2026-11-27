import { z } from "zod";

/**
 * Zod 4 хурдан ажиллахын тулд эхлээд schema бүрд `new Function`-ийг туршдаг. Content-Security-Policy
 * `unsafe-eval`-ийг хориглодог (`src/lib/security-headers.ts`) тул тэр оролдлого бүр CSP зөрчил болж
 * мэдээлэгдээд, дараа нь Zod энгийн аргаараа ажилладаг. `jitless` энэ оролдлогыг огт хийлгэхгүй. Form
 * шалгахад хэдхэн талбар тул хурдны ялгаа мэдэгдэхгүй.
 *
 * Zod ашигладаг browser-ийн файл бүр schema үүсгэхээс өмнө `import "@/lib/zod-jitless"` хийнэ.
 */
z.config({ jitless: true });
