"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Undo2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import "@/lib/zod-jitless";
import { z } from "zod";
import { Field, fieldAria } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useFieldError } from "@/i18n/use-field-error";
import { useFormat } from "@/i18n/use-format";
import { useUserMessage } from "@/lib/api/use-user-message";
import { accountKeys, queryKeys } from "@/lib/query-keys";
import {
  createOrderRequest,
  REQUEST_REASONS,
  withdrawOrderRequest,
  type Order,
  type OrderRequest,
  type OrderRequestInput,
  type RequestKind,
  type RequestReason,
} from "./orders-api";

/** Захиалгын хуудас server-ийн шинэ хариуг шууд харуулна; бусад жагсаалтыг дахин татна. */
function useRequestMutation<V>(number: string, mutationFn: (variables: V) => Promise<Order>) {
  const queryClient = useQueryClient();
  const userMessage = useUserMessage();
  return useMutation({
    mutationFn,
    onSuccess: (order) => queryClient.setQueryData(queryKeys.order(number), order),
    onError: (error) => toast.error(userMessage(error)),
    // Татгалзсан бол захиалгын төлөв өөрчлөгдсөн байж болно: дахин уншина.
    onSettled: () => Promise.all(accountKeys.map((queryKey) => queryClient.invalidateQueries({ queryKey }))),
  });
}

/**
 * Цуцлах, буцаах: одоо гаргаж болох хүсэлт (`available_request`-ийг server тооцдог тул дүрмийг энд давтахгүй)
 * болон өмнөх хүсэлтүүдийн явц.
 */
export function OrderRequests({ order }: { order: Order }) {
  const t = useTranslations("orders.requests");
  const format = useFormat();
  const [open, setOpen] = useState(false);
  // Диалог нээгдэх бүрд хоосон маягт.
  const [session, setSession] = useState(0);
  const kind = order.available_request;
  if (!kind && order.requests.length === 0) return null;
  const deadline = order.return_deadline ? format.dateTime(order.return_deadline, { dateStyle: "long" }) : "";

  return (
    <section aria-labelledby="requests-heading" className="space-y-4">
      <h2 id="requests-heading" className="font-semibold">
        {t("heading")}
      </h2>
      {order.requests.length > 0 && (
        <ul className="space-y-3">
          {[...order.requests].reverse().map((request) => (
            <RequestCard key={request.id} order={order} request={request} />
          ))}
        </ul>
      )}
      {kind && (
        <div className="space-y-3">
          <p className="text-muted-foreground type-caption">
            {kind === "cancel" ? t("cancelHint") : t("returnHint", { date: deadline })}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setSession((count) => count + 1);
              setOpen(true);
            }}
          >
            {kind === "cancel" ? <XCircle aria-hidden /> : <Undo2 aria-hidden />}
            {t(kind === "cancel" ? "askCancel" : "askReturn")}
          </Button>
          <RequestDialog key={session} number={order.number} kind={kind} open={open} onClose={() => setOpen(false)} />
        </div>
      )}
    </section>
  );
}

function RequestCard({ order, request }: { order: Order; request: OrderRequest }) {
  const t = useTranslations("orders.requests");
  const withdraw = useRequestMutation(order.number, (id: number) => withdrawOrderRequest(order.number, id));
  const sendBack = request.kind === "return" && request.status === "approved" && order.return_address;
  // Зөвшөөрөгдсөн цуцлалт шууд дуусдаг тул `cancel_approved`, `cancel_received` гэж байхгүй.
  const explain = `${request.kind}_${request.status}` as "return_approved";

  return (
    <li className="bg-secondary/60 space-y-2 rounded-xl px-4 py-3 type-caption">
      <p className="flex flex-wrap items-center justify-between gap-x-3">
        <span className="font-medium">{t(`kind.${request.kind}`)}</span>
        <span className="text-muted-foreground">{t(`status.${request.status}`)}</span>
      </p>
      <p>{t(`explain.${explain}`)}</p>
      <p className="text-muted-foreground break-words">
        {t("yourReason", { reason: t(`reasons.${request.reason}`) })}
        {request.details ? ` · ${request.details}` : ""}
      </p>
      {request.decision_note && <p className="break-words">{t("fromShop", { note: request.decision_note })}</p>}
      {sendBack && (
        <div className="bg-background space-y-1 rounded-lg px-3 py-2">
          <p className="text-muted-foreground">{t("returnTo")}</p>
          <p className="font-medium">{order.return_address}</p>
          <p className="text-muted-foreground">{t("quoteNumber", { number: order.number })}</p>
        </div>
      )}
      {request.status === "requested" && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={withdraw.isPending}
          onClick={() => withdraw.mutate(request.id, { onSuccess: () => toast.success(t("withdrawn")) })}
        >
          {t(withdraw.isPending ? "withdrawing" : "withdraw")}
        </Button>
      )}
    </li>
  );
}

const schema = z
  .object({
    reason: z.string().min(1, "requestReason"),
    details: z.string().trim().max(500, "max500"),
  })
  .refine((values) => values.reason !== "other" || values.details.length > 0, {
    path: ["details"],
    message: "requestDetails",
  });
type Values = z.infer<typeof schema>;

function RequestDialog({ number, kind, open, onClose }: { number: string; kind: RequestKind; open: boolean; onClose: () => void }) {
  const t = useTranslations("orders.requests");
  const fieldError = useFieldError();
  const send = useRequestMutation(number, (body: OrderRequestInput) => createOrderRequest(number, body));
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { reason: "", details: "" } });
  const other = useWatch({ control, name: "reason" }) === "other";

  const submit = handleSubmit(({ reason, details }) =>
    send.mutate(
      { kind, reason: reason as RequestReason, details: details || null },
      {
        onSuccess: () => {
          toast.success(t("sent"));
          onClose();
        },
      },
    ),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t(kind === "cancel" ? "cancelTitle" : "returnTitle")}</DialogTitle>
            <DialogDescription>{t(kind === "cancel" ? "cancelDialog" : "returnDialog")}</DialogDescription>
          </DialogHeader>
          <Field id="request-reason" label={t("reason")} error={fieldError(errors.reason?.message)}>
            <NativeSelect {...fieldAria("request-reason", errors.reason?.message)} {...register("reason")}>
              <option value="">{t("chooseReason")}</option>
              {REQUEST_REASONS[kind].map((reason) => (
                <option key={reason} value={reason}>
                  {t(`reasons.${reason}`)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="request-details" label={t(other ? "details" : "detailsOptional")} error={fieldError(errors.details?.message)}>
            <Textarea {...fieldAria("request-details", errors.details?.message)} maxLength={500} {...register("details")} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("keep")}
            </Button>
            <Button type="submit" disabled={send.isPending}>
              {t(send.isPending ? "sending" : "send")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
