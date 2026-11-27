"use client";

import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "@/components/theme/theme-provider";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const t = useTranslations("layout");
  const { resolvedTheme, setTheme } = useTheme();
  const next = resolvedTheme === "dark" ? "light" : "dark";

  // Хоёр icon-ыг хоёуланг нь үргэлж render хийж, CSS-ээр (`dark:` variant) сольдог, label тогтмол. Server
  // зочны theme-ийг мэдэхгүй тул `resolvedTheme`-ээс хамаарсан бүх зүйл server, client дээр өөр гарна
  // (hydration mismatch).
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("themeToggle")}
      onClick={() => setTheme(next)}
    >
      <Sun className="dark:hidden" />
      <Moon className="hidden dark:block" />
    </Button>
  );
}
