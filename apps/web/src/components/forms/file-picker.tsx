"use client";

import { Upload } from "lucide-react";
import type { ComponentProps, Ref } from "react";
import { cn } from "@/lib/utils";

type Props = Omit<ComponentProps<"input">, "type" | "ref" | "className"> & {
  ref?: Ref<HTMLInputElement>;
  /** Товч дээрх бичиг ("Зураг сонгох"). */
  buttonLabel: string;
  /** Сонгосон файлын нэр, эсвэл "сонгоогүй" гэсэн бичиг. */
  fileName: string;
};

/**
 * Файл сонгох талбар, сайтын хэлээр. Хөтчийн өөрийн товч хөтчийн хэлээр ("Choose File") гардаг тул
 * жинхэнэ input-ыг ил харагдахгүйгээр дээр нь дэлгэж тавина: дарах, чирж тавих, гараар сонгох бүгд
 * хэвээр ажиллана. Нэрийг дуудагчийн `<label>` өгнө.
 */
export function FilePicker({ buttonLabel, fileName, ref, ...input }: Props) {
  return (
    <div className="border-field bg-background has-[:focus-visible]:ring-ring/50 has-[[aria-invalid=true]]:border-destructive relative flex min-h-11 items-center gap-3 rounded-xl border px-2 has-[:focus-visible]:ring-3">
      <span aria-hidden className={cn("bg-secondary inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm font-medium")}>
        <Upload className="size-3.5" /> {buttonLabel}
      </span>
      <span className="text-muted-foreground min-w-0 truncate text-sm">{fileName}</span>
      <input ref={ref} type="file" className="absolute inset-0 size-full cursor-pointer opacity-0" {...input} />
    </div>
  );
}
