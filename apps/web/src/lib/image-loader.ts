import { env } from "@/lib/env";

const MEDIA_PREFIX = `${env.NEXT_PUBLIC_API_URL}/media/`;

/**
 * API каталогийн зураг бүрийг 400, 800 px WebP (`..._400.webp`, `..._800.webp`) болгон бэлэн өгдөг. Тиймээс
 * Next-ийн optimizer зөвхөн дахин encode хийх байсан (бас `localhost`-оос зураг авахыг зөвшөөрдөггүй). Энэ
 * loader хүссэн өргөнд хамгийн ойр бэлэн хэмжээг сонгож, энэ сайтын өөрийн `/media` route-оор
 * (`next.config.ts`) татна. Өөр origin ашиглавал эхний зураг ирэхээс өмнө DNS lookup, TCP handshake,
 * холболтын эхний удаан үе (congestion window) хүлээх болно, хуудасны largest paint яг үүнийг хүлээдэг.
 */
export default function imageLoader({ src, width }: { src: string; width: number }): string {
  const sized = width > 400 ? src.replace(/_400\.webp$/, "_800.webp") : src.replace(/_800\.webp$/, "_400.webp");
  return sized.startsWith(MEDIA_PREFIX) ? sized.slice(env.NEXT_PUBLIC_API_URL.length) : sized;
}
