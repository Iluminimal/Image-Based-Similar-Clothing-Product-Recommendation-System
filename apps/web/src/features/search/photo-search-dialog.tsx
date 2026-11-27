"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ImageDropzone } from "./image-dropzone";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Хайлтын талбарын камерын товчоор нээгдэх зураг сонгогч. Зураг авах бүх аргыг (upload, drop, paste, камер,
 * HEIC) дахин ашиглана. Зураг сонговол search store-д хадгалагдаж, /search хуудас хайлтыг ажиллуулна. Dialog
 * library татдаг тул анх товшиход л ачаална.
 */
export function PhotoSearchDialog({ open, onOpenChange }: Props) {
  const t = useTranslations("search.dialog");
  const router = useRouter();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        <ImageDropzone
          size="compact"
          listenForPaste={open}
          onPicked={() => {
            onOpenChange(false);
            router.push("/search");
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
