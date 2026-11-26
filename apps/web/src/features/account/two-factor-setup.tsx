"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Field, fieldAria } from "@/components/forms/form-field";
import { PasswordInput } from "@/components/forms/password-input";
import { Button } from "@/components/ui/button";
import { FormAlert } from "@/components/ui/form-alert";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { useUserMessage } from "@/lib/api/use-user-message";
import { twoFactorKey, useEnableTwoFactor, useSetupTwoFactor } from "./use-two-factor";

/**
 * Баталгаажуулагч апп холбох гурван алхам: нууц үг -> QR уншуулж кодоо оруулах -> нөөц кодоо хадгалах.
 * Төлөвийн query-г зөвхөн "Хадгаллаа" дарсны дараа шинэчилнэ: эс бөгөөс энэ дэлгэц алга болж нөөц код
 * дахин харагдахгүй.
 */
export function TwoFactorSetup() {
  const t = useTranslations("account.twoFactor");
  const userMessage = useUserMessage();
  const queryClient = useQueryClient();
  const setup = useSetupTwoFactor();
  const enable = useEnableTwoFactor();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  async function run(event: FormEvent, action: () => Promise<unknown>) {
    event.preventDefault();
    setProblem(null);
    try {
      await action();
    } catch (error) {
      setProblem(
        error instanceof ApiError && error.is("invalidCredentials") ? t("wrongPassword") : userMessage(error),
      );
    }
  }

  if (enable.data) {
    return (
      <div className="space-y-4">
        <p className="type-caption">{t("recoveryHelp")}</p>
        <ul aria-label={t("recoveryLabel")} className="bg-muted grid grid-cols-2 gap-x-6 gap-y-1 rounded-xl p-4 font-mono text-sm">
          {enable.data.codes.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void navigator.clipboard?.writeText(enable.data.codes.join("\n"))}>
            {t("copy")}
          </Button>
          <Button type="button" onClick={() => void queryClient.invalidateQueries({ queryKey: twoFactorKey })}>
            {t("saved")}
          </Button>
        </div>
      </div>
    );
  }

  if (setup.data) {
    return (
      <form noValidate className="space-y-4" aria-label={t("scanTitle")} onSubmit={(event) => void run(event, () => enable.mutateAsync(code))}>
        <p className="type-caption">{t("scan")}</p>
        {/* eslint-disable-next-line @next/next/no-img-element -- data: URI SVG, next/image-д хэрэггүй */}
        <img src={setup.data.qr_image} alt={t("qrAlt")} width={200} height={200} className="rounded-lg bg-white" />
        <p className="text-muted-foreground type-caption">
          {t("manual")} <code className="text-foreground break-all select-all">{setup.data.secret}</code>
        </p>
        <Field id="totp-enable-code" label={t("code")}>
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
            {...fieldAria("totp-enable-code")}
          />
        </Field>
        {problem && <FormAlert>{problem}</FormAlert>}
        <Button type="submit" disabled={enable.isPending || code.length < 6}>
          {enable.isPending && <Loader2 className="animate-spin" />} {t("enable")}
        </Button>
      </form>
    );
  }

  return (
    <form noValidate className="space-y-4" aria-label={t("startLabel")} onSubmit={(event) => void run(event, () => setup.mutateAsync(password))}>
      <Field id="totp-password" label={t("password")}>
        <PasswordInput
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          {...fieldAria("totp-password")}
        />
      </Field>
      {problem && <FormAlert>{problem}</FormAlert>}
      <Button type="submit" disabled={setup.isPending || !password}>
        {setup.isPending && <Loader2 className="animate-spin" />} {t("start")}
      </Button>
    </form>
  );
}
