import { useTranslations } from "next-intl";
import type { CSSProperties, ReactNode } from "react";
import { Reveal } from "@/components/motion/reveal";
import { ProductCard, ProductCardSkeleton } from "@/components/product/product-card";
import type { Product } from "@/features/catalog/product";
import { cn } from "@/lib/utils";

const GRID = "grid grid-cols-2 gap-x-3 gap-y-8 sm:grid-cols-3 sm:gap-x-5 lg:gap-x-6";

export function ProductGrid({
  products,
  columns = 4,
  priorityCount = 4,
  headingLevel = 2,
  className,
}: {
  products: Product[];
  columns?: 3 | 4;
  priorityCount?: number;
  headingLevel?: 2 | 3;
  className?: string;
}) {
  return (
    <ul className={cn(GRID, columns === 4 && "lg:grid-cols-4", className)}>
      {products.map((product, i) => {
        const card = <ProductCard product={product} priority={i < priorityCount} headingLevel={headingLevel} />;
        // Хуудасны хурдыг эхний мөрөөр хэмждэг тул тэр анхнаасаа харагдана.
        if (i < priorityCount) {
          // Зөвхөн `translate`, `scale` (opacity-гүй): эхний мөр хэзээ ч нуугдахгүй, LCP удаашрахгүй.
          return (
            <li key={product.id} className="card-in" style={{ "--i": i } as CSSProperties}>
              {card}
            </li>
          );
        }
        return (
          // Эхний дэлгэцээс доорх мөрүүдийг ойртох хүртэл зурахгүй (зургийг нь ч татахгүй). Орж ирэхдээ
          // доороос дээш гарна.
          <Reveal
            key={product.id}
            as="li"
            delay={((i - priorityCount) % 4) * 0.06}
            y={14}
            className={i >= priorityCount + 3 ? "defer-render [contain-intrinsic-size:auto_380px]" : undefined}
          >
            {card}
          </Reveal>
        );
      })}
    </ul>
  );
}

export function ProductGridSkeleton({
  count = 8,
  columns = 4,
}: {
  count?: number;
  columns?: 3 | 4;
}): ReactNode {
  const t = useTranslations("layout.ui");
  return (
    <div
      className={cn(GRID, columns === 4 && "lg:grid-cols-4")}
      role="status"
      aria-label={t("loadingProducts")}
    >
      {Array.from({ length: count }, (_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}
