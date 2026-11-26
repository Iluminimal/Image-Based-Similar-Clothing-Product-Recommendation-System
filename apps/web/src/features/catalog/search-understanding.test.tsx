import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { testIntl } from "@/test/intl";
import { SearchUnderstanding } from "./search-understanding";

describe("SearchUnderstanding", () => {
  it("shows what was understood and which words were left out", () => {
    testIntl.locale = "mn";
    render(
      <SearchUnderstanding
        interpretation={{
          applied: [
            { key: "color", value: "Red" },
            { key: "article_type", value: "Dresses" },
          ],
          ignored: ["цэцэгтэй", "урт"],
        }}
      />,
    );

    expect(screen.getByText("Төрөл: Даашинз")).toBeInTheDocument();
    expect(screen.getByText("Эдгээр үгийг ойлгоогүй тул хайлтад тооцсонгүй: цэцэгтэй, урт")).toBeInTheDocument();
  });

  it("says nothing about ignored words when every word was used", () => {
    render(
      <SearchUnderstanding
        interpretation={{ applied: [{ key: "article_type", value: "Dresses" }], ignored: [] }}
      />,
    );

    expect(screen.getByText("Type: Dresses")).toBeInTheDocument();
    expect(screen.queryByText(/Not recognised/)).not.toBeInTheDocument();
  });
});
