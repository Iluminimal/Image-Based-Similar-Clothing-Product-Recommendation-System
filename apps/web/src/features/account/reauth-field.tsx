"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Field, fieldAria } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SessionUser } from "@/features/auth/auth-store";
import { useCountdown } from "@/features/auth/use-countdown";
import { ApiError } from "@/lib/api/errors";
import { useUserMessage } from "@/lib/api/use-user-message";
import { useRequestReauth } from "./use-contact";

/**
 * Нууц үггүй бүртгэлийн эмзэг үйлдэл: нэвтэрсэн байх нь хангалтгүй тул имэйл (байхгүй бол утас) руу
 * шинэ код авч оруулна. Нууц үгтэй бүртгэл нууц үгээ бичдэг тул үүнийг хэрэглэхгүй.
 */
export function ReauthField({
  id,
  user,
  value,
  onChange,
}: {
  id: string;
  user: SessionUser;
  value: string;
  onChange: (code: string) => void;
}) {
  const t = useTranslations("account.reauth");
  const userMessage = useUserMessage();
  const request = useRequestReauth();
  const countdown = useCountdown();
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const destination = user.email ?? user.phone ?? "";

  async function send() {
    setProblem(null);
    try {
      await request.mutateAsync();
      setSent(true);
      countdown.start(60);
    } catch (error) {
      if (error instanceof ApiError && error.retryAfter) countdown.start(error.retryAfter);
      setProblem(userMessage(error));
    }
  }

  return (
    <div className="space-y-2">
      <Field id={id} label={t("label")} hint={sent ? t("sent", { destination }) : t("hint", { destination })}>
        <Input
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/\D/g, ""))}
          {...fieldAria(id, undefined, "hint")}
        />
      </Field>
      <Button type="button" variant="outline" disabled={request.isPending || countdown.remaining > 0} onClick={() => void send()}>
        {request.isPending && <Loader2 className="animate-spin" />}
        {countdown.remaining > 0 ? t("resendIn", { seconds: countdown.remaining }) : t(sent ? "resend" : "send")}
      </Button>
      {problem && (
        <p role="alert" className="text-destructive type-caption">
          {problem}
        </p>
      )}
    </div>
  );
}
