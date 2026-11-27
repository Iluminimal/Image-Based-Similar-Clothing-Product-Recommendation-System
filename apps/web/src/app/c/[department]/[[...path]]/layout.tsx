import { resolveTrail } from "@/features/catalog/category-trail";

/**
 * Ангиллыг хуудас stream хийж эхлэхээс өмнө энд шалгана. Хуудас `loading.tsx`-ийн ард ачаалагддаг тул тэнд
 * `notFound()` дуудахад хариу аль хэдийн 200 статустай явсан байдаг. Харин layout жинхэнэ 404 өгнө. Хайлтын
 * систем устсан URL-ыг хасахдаа яг үүнийг хүлээдэг.
 */
export default async function CategoryLayout({ children, params }: LayoutProps<"/c/[department]/[[...path]]">) {
  await resolveTrail(params);
  return children;
}
