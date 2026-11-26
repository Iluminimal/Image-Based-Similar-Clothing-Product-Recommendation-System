"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { SessionUser } from "@/features/auth/auth-store";
import { TwoFactorSetup } from "./two-factor-setup";
import { useTwoFactorStatus } from "./use-two-factor";

/** Ажилтны профайл дээрх хоёр шатлалт нэвтрэлт. Унтраах нь зөвхөн серверийн command-оор. */
export function TwoFactorCard({ user }: { user: SessionUser }) {
  const t = useTranslations("account.twoFactor");
  const { data } = useTwoFactorStatus(user.id);
  return (
    <section className="tile space-y-5 p-6 sm:p-8">
      <header className="space-y-1">
        <h2 className="type-heading">{t("title")}</h2>
        <p className="text-muted-foreground type-caption">{t("description")}</p>
      </header>
      {data?.enabled ? (
        <div className="space-y-1">
          <p className="text-success inline-flex items-center gap-1.5 type-caption">
            <ShieldCheck aria-hidden className="size-4" /> {t("on")}
          </p>
          <p className="text-muted-foreground type-caption">{t("recoveryLeft", { count: data.recovery_codes_left })}</p>
          <p className="text-muted-foreground type-caption">{t("lost")}</p>
        </div>
      ) : data ? (
        <TwoFactorSetup />
      ) : null}
    </section>
  );
}
