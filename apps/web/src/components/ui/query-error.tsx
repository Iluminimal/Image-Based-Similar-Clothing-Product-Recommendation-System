"use client";

import { Button } from "@/components/ui/button";
import { useUserMessage } from "@/lib/api/use-user-message";

/**
 * Өгөгдөл ачаалж чадаагүй үед харуулах нийтлэг хэсэг: ойлгомжтой алдааны мессеж, "Дахин оролдох" товч. Админ
 * болон дэлгүүрийн жагсаалт, дэлгэрэнгүй хуудсууд ашиглана.
 */
export function QueryError({ error, onRetry, retryLabel }: { error: unknown; onRetry: () => unknown; retryLabel: string }) {
  const message = useUserMessage();
  return (
    <div className="space-y-3">
      <p role="alert" className="text-destructive-text">
        {message(error)}
      </p>
      <Button variant="outline" onClick={() => void onRetry()}>
        {retryLabel}
      </Button>
    </div>
  );
}
