"use client";

import { useEffect, useRef, type CSSProperties, type ElementType, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  as?: "div" | "li" | "section" | "p";
  /** Хүлээх хугацаа (секунд). Зэрэгцээ элементүүдэд бага зэрэг өсгөж өгвөл дараалж гарч ирнэ. */
  delay?: number;
  /** Доороос дээш хөөрөх зай, px. */
  y?: number;
  /** `view`: scroll хийж харагдах үед (fold-оос доор). `mount`: гарч ирмэгц. */
  when?: "view" | "mount";
  className?: string;
};

/**
 * Элемент нэг удаа аажмаар тодорч байрандаа орно. Animation өөрөө CSS (globals.css дахь `[data-reveal]`). Энэ
 * component зөвхөн зөв үед `data-in` тавьдаг тул animation сан татах шаардлагагүй. Эхний дэлгэцийн хамгийн
 * том элементийг үүгээр бүү ороо: эхэндээ нуугддаг тул хуудасны largest contentful paint хоцорно. Script-гүй
 * эсвэл reduced motion үед агуулга шууд харагдана.
 */
export function Reveal({ children, as = "div", delay = 0, y = 18, when = "view", className }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const show = () => element.setAttribute("data-in", "");
    if (when === "mount" || typeof IntersectionObserver === "undefined") {
      // Нэг frame хүлээнэ: нуугдсан төлөв эхлээд зурагдсаны дараа солигдож, transition ажиллана.
      const frame = requestAnimationFrame(show);
      return () => cancelAnimationFrame(frame);
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          show();
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [when]);

  const Component = as as ElementType;
  return (
    <Component
      ref={ref}
      data-reveal=""
      className={className}
      style={{ "--reveal-delay": `${delay}s`, "--reveal-y": `${y}px` } as CSSProperties}
    >
      {children}
    </Component>
  );
}
