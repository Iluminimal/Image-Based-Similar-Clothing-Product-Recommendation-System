import { beforeEach, describe, expect, it, vi } from "vitest";
import { listProducts } from "@/features/catalog/api";
import { sampleProducts } from "./home-data";

vi.mock("server-only", () => ({}));
vi.mock("@/features/catalog/api", () => ({ listProducts: vi.fn() }));

/** Эрэгтэй, эмэгтэй хоёуланд харагддаг (Unisex) бараа хоёр жагсаалтын эхэнд байж болно. */
function catalogue(byDepartment: Record<string, number[]>) {
  vi.mocked(listProducts).mockImplementation(async (query, count) => {
    const ids = byDepartment[query.department ?? "footwear"] ?? [];
    return { items: ids.slice(0, count).map((id) => ({ id })) } as never;
  });
}

describe("sampleProducts", () => {
  beforeEach(() => {
    vi.mocked(listProducts).mockReset();
  });

  it("offers three different photos even when one product leads two lists", async () => {
    catalogue({ women: [57, 12], men: [57, 31], footwear: [8] });

    const samples = await sampleProducts();

    expect(samples.map((product) => product.id)).toEqual([57, 31, 8]);
  });

  it("offers fewer photos rather than the same one twice", async () => {
    catalogue({ women: [57], men: [57], footwear: [] });

    expect((await sampleProducts()).map((product) => product.id)).toEqual([57]);
  });
});
