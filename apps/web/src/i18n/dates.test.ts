import { describe, expect, it } from "vitest";
import { formatDate } from "./dates";

const mn = (value: string, options: Intl.DateTimeFormatOptions) => formatDate(value, options, "mn-MN");

describe("formatDate", () => {
  const afternoon = "2026-11-03T04:05:00Z"; // Улаанбаатарт 12:05

  it.each<[string, Intl.DateTimeFormatOptions, string]>([
    ["a medium date", { dateStyle: "medium" }, "2026 оны 11-р сарын 3"],
    ["a long date", { dateStyle: "long" }, "2026 оны 11-р сарын 3"],
    ["a date with time", { dateStyle: "medium", timeStyle: "short" }, "2026 оны 11-р сарын 3, 12:05"],
    ["a day without the year", { month: "short", day: "numeric" }, "11-р сарын 3"],
    ["a day with its weekday", { weekday: "short", month: "short", day: "numeric" }, "11-р сарын 3. Мя"],
    ["no options", {}, "2026 оны 11-р сарын 3"],
  ])("writes %s in Mongolian without the browser's Mongolian data", (_name, options, expected) => {
    expect(mn(afternoon, options)).toBe(expected);
  });

  it("uses the shop's day, so the server and the browser agree wherever they run", () => {
    const lateUtc = "2026-11-02T20:30:00Z"; // Улаанбаатарт 11-р сарын 3-ны 04:30

    expect(mn(lateUtc, { dateStyle: "medium", timeStyle: "short" })).toBe("2026 оны 11-р сарын 3, 04:30");
    expect(formatDate(lateUtc, { dateStyle: "medium" }, "en-US")).toBe("Nov 3, 2026");
  });

  it("keeps a calendar day as it is when asked for UTC (the revenue chart)", () => {
    expect(mn("2026-11-02T00:00:00Z", { month: "short", day: "numeric", timeZone: "UTC" })).toBe("11-р сарын 2");
  });

  it("writes midnight as 00, not 24", () => {
    expect(mn("2026-11-02T16:00:00Z", { dateStyle: "medium", timeStyle: "short" })).toBe("2026 оны 11-р сарын 3, 00:00");
  });

  it("leaves English to the browser", () => {
    expect(formatDate(afternoon, { dateStyle: "long" }, "en-US")).toBe("November 3, 2026");
  });
});
