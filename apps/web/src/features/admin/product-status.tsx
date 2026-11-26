"use client";

/**
 * Барааг зарах эсэхийг солих. Нэг даралтаар шууд солигдож, "Буцаах" санал болгоно (баталгаажуулах
 * цонхгүй). Дэлгэц дээр тэр даруй харагдаж, сервер татгалзвал хуучин байдалдаа буцна.
 */
import { useMutation, useMutationState, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { StatusDot } from "@/components/admin/status-dot";
import { Switch } from "@/components/ui/switch";
import { useUserMessage } from "@/lib/api/use-user-message";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { setAdminProductActive, type AdminProduct, type AdminProductPage } from "./admin-api";

const STATUS_MUTATION = ["admin", "product-status"] as const;

type Change = { id: number; active: boolean; name: string; held: number; isUndo?: boolean };

/** Кэшэд байгаа жагсаалтууд (табын тоотой нь) ба барааны хуудсанд шинэ төлөвийг харуулна. */
function showStatus(queryClient: QueryClient, id: number, active: boolean) {
  queryClient.setQueriesData<AdminProductPage>({ queryKey: queryKeys.admin.products }, (page) => {
    const item = page?.items.find((product) => product.id === id);
    if (!page || !item || item.is_active === active) return page;
    const step = active ? 1 : -1;
    return {
      ...page,
      items: page.items.map((product) => (product.id === id ? { ...product, is_active: active } : product)),
      status_counts: {
        ...page.status_counts,
        active: page.status_counts.active + step,
        inactive: page.status_counts.inactive - step,
      },
    };
  });
  queryClient.setQueryData<AdminProduct>(queryKeys.admin.product(id), (product) => product && { ...product, is_active: active });
}

export function useProductStatus() {
  const t = useTranslations("admin.productStatus");
  const userMessage = useUserMessage();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationKey: STATUS_MUTATION,
    mutationFn: ({ id, active }: Change) => setAdminProductActive(id, active),
    onMutate: async ({ id, active }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.admin.products });
      showStatus(queryClient, id, active);
    },
    onError: (error, { id, active }) => {
      showStatus(queryClient, id, !active);
      toast.error(userMessage(error));
    },
    onSuccess: (_product, change) => {
      const message = t(change.active ? "nowOnSale" : "nowStopped", { name: change.name });
      if (change.isUndo) {
        toast.success(message);
        return;
      }
      toast.success(message, {
        description: !change.active && change.held > 0 ? t("heldUnaffected", { count: change.held }) : undefined,
        action: { label: t("undo"), onClick: () => mutation.mutate({ ...change, active: !change.active, isUndo: true }) },
        duration: 8000,
      });
    },
    // Дэлгэц дээрх жагсаалтыг шууд дахин татахгүй: төлвөөр шүүсэн таб дээр мөр алга болбол буцаахад
    // хэцүү. Дараа нь таб, хуудас солиход шинэчлэгдэнэ.
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.products, refetchType: "none" }),
        queryClient.invalidateQueries({ queryKey: ["admin", "product"], refetchType: "none" }),
      ]),
  });

  const pending = useMutationState({
    filters: { mutationKey: STATUS_MUTATION, status: "pending" },
    select: (running) => (running.state.variables as Change).id,
  });

  return {
    change: (product: AdminProduct, active: boolean) =>
      mutation.mutate({ id: product.id, active, name: product.name, held: product.committed }),
    isChanging: (id: number) => pending.includes(id),
  };
}

type Props = {
  product: AdminProduct;
  /** Агуулахын ажилтан л солино; бусдад төлөв зөвхөн харагдана. */
  canEdit: boolean;
  /** Зарагдаж байгаа ч үлдэгдэлгүй бол анхааруулах. */
  warnWhenEmpty?: boolean;
};

export function ProductStatus({ product, canEdit, warnWhenEmpty = true }: Props) {
  const t = useTranslations("admin.productStatus");
  const { change, isChanging } = useProductStatus();
  const text = t(product.is_active ? "onSale" : "stopped");
  if (!canEdit) return <StatusDot tone={product.is_active ? "success" : "neutral"}>{text}</StatusDot>;

  const busy = isChanging(product.id);
  return (
    <div className="space-y-0.5">
      <label className="flex min-h-11 w-fit cursor-pointer items-center gap-2.5 text-sm whitespace-nowrap">
        <Switch
          checked={product.is_active}
          disabled={busy}
          aria-label={t("switchLabel", { name: product.name })}
          onCheckedChange={(active) => change(product, active)}
        />
        {/* Унтраалга төлвөө өөрөө хэлдэг тул дэлгэц уншигчид энэ бичгийг давтахгүй. */}
        <span aria-hidden className={cn(!product.is_active && "text-muted-foreground")}>
          {text}
        </span>
        {busy && <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />}
      </label>
      {warnWhenEmpty && product.is_active && product.stock_quantity === 0 && (
        <p className="text-warning-foreground text-xs">{t("outOfStock")}</p>
      )}
    </div>
  );
}
