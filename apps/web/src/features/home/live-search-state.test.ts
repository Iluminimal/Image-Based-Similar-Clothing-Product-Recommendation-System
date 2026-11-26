import { describe, expect, it } from "vitest";
import { makeGarmentResponse } from "@/test/fixtures";
import { classifyError, demoReducer, IDLE, type DemoState } from "./live-search-state";

const file = new File(["x"], "photo.jpg", { type: "image/jpeg" });
const garments = makeGarmentResponse([{}, {}, {}]).garments;

function scanning(): DemoState {
  return demoReducer(IDLE, { type: "scan", previewUrl: "blob:one", file });
}

describe("demoReducer", () => {
  it("goes idle -> scanning -> done, starting on the first garment", () => {
    const done = demoReducer(scanning(), { type: "found", garments, totalMs: 120 });

    expect(done).toMatchObject({ phase: "done", previewUrl: "blob:one", totalMs: 120, focus: 0 });
    expect(done.phase === "done" && done.garments).toHaveLength(3);
  });

  it("ignores a result that arrives when nothing is being scanned", () => {
    expect(demoReducer(IDLE, { type: "found", garments, totalMs: 1 })).toBe(IDLE);
  });

  it("moves focus between garments but never outside them", () => {
    const done = demoReducer(scanning(), { type: "found", garments, totalMs: 1 });

    expect(demoReducer(done, { type: "focus", index: 2 })).toMatchObject({ focus: 2 });
    expect(demoReducer(done, { type: "focus", index: 9 })).toMatchObject({ focus: 2 });
    expect(demoReducer(done, { type: "focus", index: -4 })).toMatchObject({ focus: 0 });
    expect(demoReducer(IDLE, { type: "focus", index: 1 })).toBe(IDLE);
  });

  it("keeps the photo when a scan fails so it can be retried, and has none when the photo itself was unreadable", () => {
    expect(demoReducer(scanning(), { type: "failed", error: "network" })).toEqual({ phase: "error", error: "network", previewUrl: "blob:one", file });
    expect(demoReducer(IDLE, { type: "failed", error: "unreadable" })).toEqual({ phase: "error", error: "unreadable", previewUrl: null, file: null });
  });

  it("starts over on reset", () => {
    expect(demoReducer(scanning(), { type: "reset" })).toBe(IDLE);
  });
});

describe("classifyError", () => {
  it("tells rate limits and unreadable photos apart from network trouble", () => {
    expect(classifyError({ status: 429 })).toBe("rate");
    expect(classifyError({ status: 422 })).toBe("unreadable");
    expect(classifyError({ status: 413 })).toBe("unreadable");
    expect(classifyError({ status: 500 })).toBe("network");
    expect(classifyError({ status: 0 })).toBe("network");
    expect(classifyError(new TypeError("fetch failed"))).toBe("network");
    expect(classifyError(null)).toBe("network");
  });
});
