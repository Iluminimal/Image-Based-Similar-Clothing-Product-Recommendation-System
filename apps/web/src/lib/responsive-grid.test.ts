import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE = join(process.cwd(), "src");

function components(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return components(path);
    return path.endsWith(".tsx") && !path.endsWith(".test.tsx") ? [path] : [];
  });
}

/**
 * `grid lg:grid-cols-…` утсан дээр багана заадаггүй. Тэгвэл далд (`auto`) багана мөр нь таслагддаггүй хамгийн
 * урт бичвэрийн (`truncate`, урт имэйл) хэмжээгээр тэлж, хуудсыг дэлгэцээс гаргадаг (checkout 176px,
 * dashboard 378px хэтэрч байсан). Суурь `grid-cols-1` бол `minmax(0,1fr)` тул тэлдэггүй.
 */
describe("grids that only get columns on wider screens", () => {
  it("also say how the phone's single column is sized", () => {
    const unsized = components(SOURCE).flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(/"([^"\n]*)"/g)]
        .map((match) => match[1]!.split(/\s+/))
        .filter(
          (classes) =>
            classes.includes("grid") &&
            classes.some((c) => /^(sm|md|lg|xl|2xl):grid-cols-/.test(c)) &&
            !classes.some((c) => c.startsWith("grid-cols-")),
        )
        .map((classes) => `${relative(SOURCE, file)}: ${classes.join(" ")}`),
    );

    expect(unsized).toEqual([]);
  });
});
