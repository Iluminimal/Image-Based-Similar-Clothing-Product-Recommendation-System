"use client";

import { LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

const loadFeatures = () => import("./features").then((module) => module.default);

/**
 * CSS хүрэлцэхгүй цөөн газарт хэрэглэх animation engine (жишээ нь устгахад гулсаж хаагддаг сагсны мөр).
 * Scroll reveal, hero, header CSS-ээр хийгддэг тул үүнийг ачаалдаггүй. Зөвхөн animation хийдэг хэсгийг үүгээр
 * орооно: тэр хэсэг харагдах үед л engine татагдана. `reducedMotion="user"` тул transform animation үйлдлийн
 * системийн тохиргоог дагана.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadFeatures} strict>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </LazyMotion>
  );
}
