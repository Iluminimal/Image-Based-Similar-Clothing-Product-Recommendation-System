"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, PackageCheck, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import "@/lib/zod-jitless";
import { z } from "zod";
import { Panel } from "@/components/admin/panel";
import { Field, fieldAria } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/auth-store";
import { useFieldError } from "@/i18n/use-field-error";
import type { AdminOrder, AdminOrderRequest } from "./admin-api";
import { useDates } from "./format";
import { openRequestOf } from "./open-request";
import { useApproveRequest, useDeclineRequest, useReceiveReturn } from "./use-admin";

type Decision = "approve" | "decline" | "receive";

/**
 * Энэ хүсэлт дээр одоо хэн юу хийх вэ (бусдыг API татгалзана): шийдвэр админых, барааг хүлээн авах
 * нь агуулахын ажилтных.
 */
export function requestActions(request: AdminOrderRequest | undefined, role: string | undefined) {
  const admin = role === "admin";
  return {
    approve: admin && request?.status === "requested",
    // Зөвшөөрсөн буцаалтын бараа ирэхгүй бол хаана.
    decline: admin && (request?.status === "requested" || request?.status === "approved"),
    receive: role === "warehouse" && request?.kind === "return" && request.status === "approved",
  };
}

function hint(request: AdminOrderRequest, role: string | undefined) {
  if (request.status === "received") return "hintRefund" as const;
  if (request.status === "approved") return role === "admin" ? ("hintGoods" as const) : null;
  if (role === "admin") return null;
  return request.kind === "cancel" ? ("hintHold" as const) : ("hintDecision" as const);
}

function Summary({ request }: { request: AdminOrderRequest }) {
  const t = useTranslations("admin.requests");
  const reasons = useTranslations("orders.requests.reasons");
  const dates = useDates();
  return (
    <div className="space-y-1 text-sm">
      <p className="flex flex-wrap items-center justify-between gap-x-3">
        <span className="font-medium">{t(`kind.${request.kind}`)}</span>
        <span className="text-muted-foreground">{t(`status.${request.status}`)}</span>
      </p>
      <p className="break-words">
        {t("reason", { reason: reasons(request.reason) })}
        {request.details ? ` · ${request.details}` : ""}
      </p>
      <p className="text-muted-foreground text-xs">{t("asked", { date: dates.when(request.created_at) })}</p>
      {request.decision_note && <p className="text-muted-foreground break-words">{t("reply", { note: request.decision_note })}</p>}
      {request.restocked !== null && (
        <p className="text-muted-foreground">{t(request.restocked ? "restocked" : "notRestocked")}</p>
      )}
    </div>
  );
}

/** Захиалгын хуудсан дээрх хэрэглэгчийн хүсэлт: нээлттэй нь үйлдэлтэйгээ, өмнөх нь товч. */
export function OrderRequestPanel({ order }: { order: AdminOrder }) {
  const t = useTranslations("admin.requests");
  const role = useAuth((state) => state.user?.role);
  const [dialog, setDialog] = useState<Decision | null>(null);
  // Диалог нээгдэх бүрд хоосон маягт.
  const [session, setSession] = useState(0);
  if (order.requests.length === 0) return null;
  const open = openRequestOf(order);
  const earlier = order.requests.filter((request) => request.id !== open?.id).reverse();
  const can = requestActions(open, role);
  const note = open && hint(open, role);
  const show = (next: Decision) => {
    setSession((count) => count + 1);
    setDialog(next);
  };
  const close = () => setDialog(null);

  return (
    <Panel id="request-heading" title={t("title")}>
      <div className="space-y-4">
        {open && (
          <div className="space-y-3">
            <Summary request={open} />
            {note && (
              <p role="status" className="bg-warning/20 rounded-lg px-3 py-2 text-sm">
                {t(note)}
              </p>
            )}
            {(can.approve || can.decline || can.receive) && (
              <div className="flex flex-wrap gap-2">
                {can.approve && (
                  <Button onClick={() => show("approve")}>
                    <Check aria-hidden /> {t("approve")}
                  </Button>
                )}
                {can.receive && (
                  <Button onClick={() => show("receive")}>
                    <PackageCheck aria-hidden /> {t("receive")}
                  </Button>
                )}
                {can.decline && (
                  <Button variant="outline" onClick={() => show("decline")}>
                    <X aria-hidden /> {t(open.status === "approved" ? "closeNoRefund" : "decline")}
                  </Button>
                )}
              </div>
            )}
            <ApproveDialog key={`approve-${session}`} number={order.number} request={open} open={dialog === "approve"} onClose={close} />
            <DeclineDialog key={`decline-${session}`} number={order.number} request={open} open={dialog === "decline"} onClose={close} />
            <ReceiveDialog key={`receive-${session}`} number={order.number} request={open} open={dialog === "receive"} onClose={close} />
          </div>
        )}
        {earlier.length > 0 && (
          <div className={open ? "border-border/70 space-y-3 border-t pt-4" : "space-y-3"}>
            {open && <h3 className="text-sm font-medium">{t("earlier")}</h3>}
            <ul className="divide-border/70 -my-2 divide-y">
              {earlier.map((request) => (
                <li key={request.id} className="py-2">
                  <Summary request={request} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}

type DialogProps = { number: string; request: AdminOrderRequest; open: boolean; onClose: () => void };

function ApproveDialog({ number, request, open, onClose }: DialogProps) {
  const t = useTranslations("admin.requests");
  const approve = useApproveRequest();
  const [message, setMessage] = useState("");
  const cancel = request.kind === "cancel";
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(cancel ? "approveCancelTitle" : "approveReturnTitle")}</DialogTitle>
          <DialogDescription>{t(cancel ? "approveCancelDesc" : "approveReturnDesc", { number })}</DialogDescription>
        </DialogHeader>
        <Field id="approve-message" label={t("messageOptional")}>
          <Textarea id="approve-message" maxLength={500} value={message} onChange={(event) => setMessage(event.target.value)} />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("notYet")}
          </Button>
          <Button
            variant={cancel ? "destructive" : "default"}
            disabled={approve.isPending}
            onClick={() =>
              approve.mutate(
                { number, requestId: request.id, note: message.trim() },
                {
                  onSuccess: () => {
                    toast.success(t("approvedToast"));
                    onClose();
                  },
                },
              )
            }
          >
            {t(approve.isPending ? "saving" : "approve")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const declineSchema = z.object({ note: z.string().trim().min(1, "adminDeclineNote").max(500, "max500") });
type DeclineValues = z.infer<typeof declineSchema>;

function DeclineDialog({ number, request, open, onClose }: DialogProps) {
  const t = useTranslations("admin.requests");
  const fieldError = useFieldError();
  const decline = useDeclineRequest();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<DeclineValues>({ resolver: zodResolver(declineSchema), defaultValues: { note: "" } });
  const approved = request.status === "approved";

  const submit = handleSubmit(({ note }) =>
    decline.mutate(
      { number, requestId: request.id, note },
      {
        onSuccess: () => {
          toast.success(t("declinedToast"));
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
            <DialogTitle>{t(approved ? "closeTitle" : "declineTitle")}</DialogTitle>
            <DialogDescription>{t(approved ? "closeDesc" : "declineDesc", { number })}</DialogDescription>
          </DialogHeader>
          <Field id="decline-message" label={t("message")} error={fieldError(errors.note?.message)}>
            <Textarea {...fieldAria("decline-message", errors.note?.message)} maxLength={500} {...register("note")} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("notYet")}
            </Button>
            <Button type="submit" variant="destructive" disabled={decline.isPending}>
              {decline.isPending ? t("saving") : t(approved ? "closeNoRefund" : "decline")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ReceiveDialog({ number, request, open, onClose }: DialogProps) {
  const t = useTranslations("admin.requests");
  const receive = useReceiveReturn();
  // Гэмтэлтэй гэж буцаасан барааг андуурч дахин зарахаас сэргийлж, анхдагчаар үлдэгдэлд нэмэхгүй.
  const [restock, setRestock] = useState(request.reason !== "defective");
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("receiveTitle")}</DialogTitle>
          <DialogDescription>{t("receiveDesc", { number })}</DialogDescription>
        </DialogHeader>
        <div className="flex items-start gap-3">
          <Checkbox id="receive-restock" checked={restock} onCheckedChange={(checked) => setRestock(checked === true)} className="mt-0.5" />
          <div className="space-y-0.5">
            <Label htmlFor="receive-restock">{t("restock")}</Label>
            <p className="text-muted-foreground text-xs">{t("restockHint")}</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("notYet")}
          </Button>
          <Button
            disabled={receive.isPending}
            onClick={() =>
              receive.mutate(
                { number, requestId: request.id, restock },
                {
                  onSuccess: () => {
                    toast.success(t("receivedToast"));
                    onClose();
                  },
                },
              )
            }
          >
            {t(receive.isPending ? "saving" : "confirmReceive")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
