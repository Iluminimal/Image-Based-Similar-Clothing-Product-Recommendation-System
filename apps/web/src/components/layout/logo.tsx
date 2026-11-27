import { cn } from "@/lib/utils";

/**
 * Angel-ийн тэмдэг: хоёр шугам, хөндлөн зураастай A үсэг, орой дээрээ halo-той. `currentColor` ашигладаг тул
 * гэрэл, харанхуй горимд текстийн өнгийг дагана. Зөвхөн чимэглэл: нэр нь үргэлж хажууд нь байдаг (харагддаг
 * эсвэл зөвхөн screen reader-т).
 */
export function AngelMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cn("size-7", className)}
    >
      <ellipse cx="16" cy="5" rx="6" ry="2" transform="rotate(-10 16 5)" strokeWidth="1.5" />
      <path d="M6.5 28.5 16 10.5l9.5 18" strokeWidth="2.4" />
      <path d="M10.8 22.6Q16 19.8 21.2 22.6" strokeWidth="2.4" />
    </svg>
  );
}

/** Тэмдэг ба нэр. `showName={false}` бол зөвхөн тэмдэг (header), нэрийг screen reader-д үлдээнэ. */
export function AngelLogo({
  className,
  markClassName,
  showName = true,
}: {
  className?: string;
  markClassName?: string;
  showName?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <AngelMark className={markClassName} />
      <span className={showName ? undefined : "sr-only"}>Angel</span>
    </span>
  );
}
