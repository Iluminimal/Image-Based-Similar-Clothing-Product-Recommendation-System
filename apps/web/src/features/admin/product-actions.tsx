"use client";

/**
 * Барааны жагсаалт, засах хуудасны үйлдлүүд: мөрийн "⋯" цэс, үнэ ба тоог жагсаалтаас шууд засах
 * цонх, устгах цонх.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, MoreHorizontal, Tag, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Field, fieldAria } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useFieldError } from "@/i18n/use-field-error";
import type { AdminProduct, AdminProductChanges } from "./admin-api";
import { useProductStatus } from "./product-status";
import { productSchema, toFormValues, togrogToMinor } from "./product-values";
import { useDeleteProducts, useUpdateProduct } from "./use-admin";

/** Цонх хаагдах animation-ы турш сүүлд харуулсан зүйлээ барина (`null` болмогц агуулга үсрэхгүй). */
function useLastShown<T>(value: T | null): T | null {
  const [shown, setShown] = useState(value);
  if (value !== null && value !== shown) setShown(value);
  return value ?? shown;
}

export function ProductMenu({ product, onPriceStock, onDelete }: { product: AdminProduct; onPriceStock: () => void; onDelete: () => void }) {
  const t = useTranslations("admin.productActions");
  return (
    // modal={false}: цэсээс нээсэн цонх руу focus саадгүй шилжинэ.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon-sm" className="size-8 rounded-full" aria-label={t("more", { name: product.name })}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-auto min-w-48">
        <DropdownMenuItem className="min-h-10 gap-2.5 px-3" onSelect={onPriceStock}>
          <Tag aria-hidden /> {t("priceStock")}
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" className="min-h-10 gap-2.5 px-3" onSelect={onDelete}>
          <Trash2 aria-hidden /> {t("delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const priceStockSchema = productSchema.pick({ price: true, stock_quantity: true });
type PriceStockValues = { price: string; stock_quantity: string };

function PriceStockForm({ product, onDone }: { product: AdminProduct; onDone: () => void }) {
  const t = useTranslations("admin.productActions");
  const form = useTranslations("admin.productForm");
  const fieldError = useFieldError();
  const update = useUpdateProduct();
  const {
    register,
    handleSubmit,
    formState: { errors, dirtyFields },
  } = useForm<PriceStockValues>({
    resolver: zodResolver(priceStockSchema),
    defaultValues: toFormValues(product),
  });

  const save = handleSubmit((values) => {
    // Зөвхөн өөрчилсөн талбарыг илгээнэ: үнэ засахад цонх нээх үеийн хуучин тоо дарж бичигдэхгүй.
    const changes: AdminProductChanges = {
      ...(dirtyFields.price ? { price_cents: togrogToMinor(values.price) } : {}),
      ...(dirtyFields.stock_quantity ? { on_hand: Number(values.stock_quantity) } : {}),
    };
    if (Object.keys(changes).length === 0) {
      onDone();
      return;
    }
    update.mutate(
      { id: product.id, changes },
      {
        onSuccess: () => {
          toast.success(t("saved"));
          onDone();
        },
      },
    );
  });

  return (
    <form onSubmit={save} noValidate className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field id="quick-price" label={form("price")} error={fieldError(errors.price?.message)}>
          <Input inputMode="numeric" autoComplete="off" {...fieldAria("quick-price", errors.price?.message)} {...register("price")} />
        </Field>
        <Field id="quick-stock" label={form("shelf")} error={fieldError(errors.stock_quantity?.message)}>
          <Input inputMode="numeric" autoComplete="off" {...fieldAria("quick-stock", errors.stock_quantity?.message)} {...register("stock_quantity")} />
        </Field>
      </div>
      <p className="text-muted-foreground text-xs">
        {form("shelfHint", { available: product.stock_quantity, committed: product.committed })}
      </p>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          {t("cancel")}
        </Button>
        <Button type="submit" disabled={update.isPending}>
          {update.isPending && <Loader2 aria-hidden className="animate-spin" />} {t("save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function PriceStockDialog({ product, onClose }: { product: AdminProduct | null; onClose: () => void }) {
  const t = useTranslations("admin.productActions");
  const shown = useLastShown(product);
  return (
    <Dialog open={product !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("priceStock")}</DialogTitle>
          <DialogDescription>{shown?.name}</DialogDescription>
        </DialogHeader>
        {shown && <PriceStockForm key={shown.id} product={shown} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

type DeleteProps = {
  /** Устгахаар сонгосон бараанууд; хаалттай бол null. */
  products: AdminProduct[] | null;
  onClose: () => void;
  onDeleted?: () => void;
};

/**
 * Устгахаас өмнөх цонх. Захиалгад орсон бараа устдаггүй: нэг бараа бол шалтгааныг хэлж оронд нь
 * зарахаа болихыг санал болгоно, олон бол боломжтойг нь устгаж, хэд үлдэхийг хэлнэ.
 */
export function DeleteProductsDialog({ products, onClose, onDeleted }: DeleteProps) {
  const t = useTranslations("admin.productActions");
  const remove = useDeleteProducts();
  const status = useProductStatus();
  const chosen = useLastShown(products) ?? [];
  const deletable = chosen.filter((product) => !product.ordered);
  const kept = chosen.length - deletable.length;
  const only = chosen.length === 1 ? chosen[0] : undefined;

  const confirm = () =>
    remove.mutate(
      deletable.map((product) => product.id),
      {
        onSuccess: ({ done, failed }) => {
          if (failed > 0) toast.error(t("deletePartial", { done, failed }));
          else toast.success(only ? t("deletedOne", { name: only.name }) : t("deletedMany", { count: done }));
          onClose();
          onDeleted?.();
        },
        onError: () => onClose(),
      },
    );

  const title =
    deletable.length === 0
      ? t(only ? "cannotTitle" : "cannotTitleMany")
      : only
        ? t("deleteTitle")
        : t("deleteTitleMany", { count: deletable.length });

  return (
    <Dialog open={products !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {deletable.length === 0
              ? t(only ? "cannotBody" : "cannotBodyMany")
              : only
                ? t("deleteBody", { name: only.name })
                : [t("deleteBodyMany", { count: deletable.length }), kept > 0 ? t("keptNote", { count: kept }) : ""].join(" ").trim()}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t(deletable.length === 0 ? "close" : "cancel")}
          </Button>
          {deletable.length === 0 ? (
            only?.is_active && (
              <Button
                onClick={() => {
                  status.change(only, false);
                  onClose();
                }}
              >
                {t("stopSelling")}
              </Button>
            )
          ) : (
            <Button variant="destructive" disabled={remove.isPending} onClick={confirm}>
              {remove.isPending && <Loader2 aria-hidden className="animate-spin" />} {t("delete")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
