import { useTranslations } from "next-intl";
import { AppliedFilters } from "@/features/search/applied-filters";
import type { SearchInterpretation } from "./product";

/**
 * Монгол үгтэй хайлтыг хэрхэн ойлгосон: юуг шүүлтүүр болгосон, аль үгийг тооцоогүй. Хэрэглэгч
 * үр дүн яагаад ийм байгааг харж, үгээ засаж чадна.
 */
export function SearchUnderstanding({ interpretation }: { interpretation: SearchInterpretation }) {
  const t = useTranslations("catalog");
  return (
    <div className="mb-6 space-y-2">
      <AppliedFilters applied={interpretation.applied} />
      {interpretation.ignored.length > 0 && (
        <p className="text-muted-foreground type-caption">
          {t("ignoredWords", { words: interpretation.ignored.join(", ") })}
        </p>
      )}
    </div>
  );
}
