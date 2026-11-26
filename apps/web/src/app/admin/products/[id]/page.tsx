import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";
import { EditProductView } from "@/features/admin/product-views";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin.meta");
  return { title: t("editProduct") };
}

export default async function EditProductPage({ params, searchParams }: PageProps<"/admin/products/[id]">) {
  const id = Number((await params).id);
  if (!Number.isSafeInteger(id) || id < 1) notFound();
  // Жагсаалтын шүүлтүүр: буцахад ижил хуудас руу очно.
  const { from } = await searchParams;
  return <EditProductView id={id} from={typeof from === "string" ? from : undefined} />;
}
