"use client";

/** Бараа нэмэх ба засах хуудас. */

import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Panel } from "@/components/admin/panel";
import { FilePicker } from "@/components/forms/file-picker";
import { Button } from "@/components/ui/button";
import { useIsWarehouse } from "@/features/auth/use-role";
import { useFieldError } from "@/i18n/use-field-error";
import { ApiError } from "@/lib/api/errors";
import { useUserMessage } from "@/lib/api/use-user-message";
import type { AdminProduct } from "./admin-api";
import { AdminPageHeader } from "./page-header";
import { DeleteProductsDialog } from "./product-actions";
import { ProductStatus } from "./product-status";
import { CurrentPhoto, ProductForm } from "./product-form";
import { buildCreateForm, imageProblem, toChanges } from "./product-values";
import {
  useAdminCategories,
  useAdminProduct,
  useCreateProduct,
  useReplaceProductImage,
  useUpdateProduct,
} from "./use-admin";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryError } from "@/components/ui/query-error";

/** Жагсаалт руу буцах хаяг. `from` нь зөвхөн жагсаалтын шүүлтүүр (`?...`) байж болно. */
export function listHref(from?: string) {
  return `/admin/products${from?.startsWith("?") ? from : ""}`;
}

function BackLink({ href = "/admin/products" }: { href?: string }) {
  const t = useTranslations("admin.productViews");
  return (
    <Link href={href} className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm">
      <ArrowLeft aria-hidden className="size-4" /> {t("allProducts")}
    </Link>
  );
}

function Loading({ label }: { label: string }) {
  return <Skeleton aria-busy aria-label={label} className="h-80 rounded-[var(--radius-tile)]" />;
}

export function NewProductView() {
  const t = useTranslations("admin.productViews");
  const router = useRouter();
  const { data: categories, error, refetch } = useAdminCategories();
  const create = useCreateProduct();

  return (
    <div className="max-w-3xl">
      <AdminPageHeader title={t("newProduct")} back={<BackLink />} />
      {error ? (
        <QueryError error={error} onRetry={refetch} retryLabel={t("tryAgain")} />
      ) : !categories ? (
        <Loading label={t("loadingCategories")} />
      ) : (
        <ProductForm
          categories={categories}
          submitLabel={t("createProduct")}
          onSubmit={async (payload, photo) => {
            if (!photo) return;
            const product = await create.mutateAsync(buildCreateForm(payload, photo));
            toast.success(t("created"));
            router.push(`/admin/products/${product.id}`);
          }}
        />
      )}
    </div>
  );
}

export function EditProductView({ id, from }: { id: number; from?: string }) {
  const t = useTranslations("admin.productViews");
  const form = useTranslations("admin.productForm");
  const userMessage = useUserMessage();
  const fieldError = useFieldError();
  const { data: product, error } = useAdminProduct(id);
  const { data: categories } = useAdminCategories();
  const update = useUpdateProduct();
  const replace = useReplaceProductImage();
  const router = useRouter();
  // Бараа өөрчлөх нь агуулахын ажилтных; админ зөвхөн харна.
  const canEdit = useIsWarehouse();
  const [photoError, setPhotoError] = useState<string>();
  const [photoName, setPhotoName] = useState<string>();
  const [deleting, setDeleting] = useState<AdminProduct[] | null>(null);
  const back = listHref(from);
  const fileInput = useRef<HTMLInputElement>(null);

  if (error) {
    return (
      <div className="max-w-3xl space-y-6">
        <BackLink href={back} />
        <p role="alert" className="text-muted-foreground">
          {error instanceof ApiError && error.isNotFound ? t("noSuch") : userMessage(error)}
        </p>
      </div>
    );
  }
  if (!product || !categories) {
    return (
      <div className="max-w-3xl space-y-6">
        <BackLink href={back} />
        <Loading label={t("loadingProduct")} />
      </div>
    );
  }

  const upload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) {
      setPhotoError(t("choosePhotoFirst"));
      return;
    }
    const problem = imageProblem(file);
    setPhotoError(problem ? fieldError(problem) : undefined);
    if (problem) return;
    try {
      await replace.mutateAsync({ id, file });
      toast.success(t("photoReplaced"));
      if (fileInput.current) fileInput.current.value = "";
      setPhotoName(undefined);
    } catch {
      // Алдааны шалтгааныг mutation hook аль хэдийн харуулсан.
    }
  };

  return (
    <div>
      <AdminPageHeader
        title={product.name}
        back={<BackLink href={back} />}
        description={<span className="text-xs">#{product.id}</span>}
        actions={
          canEdit && (
            <Button variant="outline" className="text-destructive" onClick={() => setDeleting([product])}>
              <Trash2 aria-hidden /> {t("delete")}
            </Button>
          )
        }
      />

      {/* Төлөв: хамгийн дээр, дармагц хадгалагдана (доорх маягтын "Хадгалах"-аас хамаарахгүй). */}
      <Panel id="status-heading" title={t("statusHeading")} className="mb-4 md:mb-6">
        <ProductStatus product={product} canEdit={canEdit} />
        <p className="text-muted-foreground mt-1 text-sm">{t(product.is_active ? "statusOnHint" : "statusOffHint")}</p>
      </Panel>
      <DeleteProductsDialog
        products={deleting && [product]}
        onClose={() => setDeleting(null)}
        onDeleted={() => router.push(back)}
      />

      <div className="grid grid-cols-1 items-start gap-4 md:gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <Panel id="photo-heading" title={t("photo")} className="lg:sticky lg:top-20">
          <div className="space-y-3">
            <CurrentPhoto product={product} />
            {canEdit && <p className="text-muted-foreground text-xs">{t("photoNote")}</p>}
            {canEdit && (
            <>
            <label htmlFor="new-photo" className="sr-only">
              {t("newPhoto")}
            </label>
            <FilePicker
              id="new-photo"
              ref={fileInput}
              accept="image/jpeg,image/png,image/webp"
              buttonLabel={form("choosePhoto")}
              fileName={photoName ?? form("noFile")}
              onChange={(event) => setPhotoName(event.target.files?.[0]?.name)}
              aria-invalid={Boolean(photoError)}
              aria-describedby={photoError ? "new-photo-error" : undefined}
            />
            {photoError && (
              <p id="new-photo-error" role="alert" className="text-destructive text-xs">
                {photoError}
              </p>
            )}
            <Button variant="outline" className="h-10 w-full rounded-full px-4" disabled={replace.isPending} onClick={() => void upload()}>
              {replace.isPending && <Loader2 aria-hidden className="animate-spin" />} {t("replacePhoto")}
            </Button>
            </>
            )}
          </div>
        </Panel>

        <section aria-labelledby="details-heading">
          <h2 id="details-heading" className="sr-only">
            {t("details")}
          </h2>
          {!canEdit && <p className="text-muted-foreground mb-3 text-sm">{t("readOnlyNote")}</p>}
          <ProductForm
            key={product.id}
            categories={categories}
            product={product}
            submitLabel={t("saveChanges")}
            readOnly={!canEdit}
            onSubmit={async (payload, _photo, changed) => {
              await update.mutateAsync({ id, changes: toChanges(payload, { stockChanged: changed.stock }) });
              toast.success(t("saved"));
            }}
          />
        </section>
      </div>
    </div>
  );
}
