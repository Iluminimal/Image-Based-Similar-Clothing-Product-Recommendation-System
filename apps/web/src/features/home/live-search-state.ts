import type { Garment } from "@/features/search/search-api";

export type DemoError = "network" | "rate" | "unreadable";

export type DemoState =
  | { phase: "idle" }
  | { phase: "scanning"; previewUrl: string; file: File }
  | { phase: "done"; previewUrl: string; file: File; garments: Garment[]; totalMs: number; focus: number }
  | { phase: "error"; error: DemoError; previewUrl: string | null; file: File | null };

export type DemoAction =
  | { type: "scan"; previewUrl: string; file: File }
  | { type: "found"; garments: Garment[]; totalMs: number }
  | { type: "failed"; error: DemoError }
  | { type: "focus"; index: number }
  | { type: "reset" };

export const IDLE: DemoState = { phase: "idle" };

/**
 * Нүүр хуудасны live photo search-ийн төлөв: idle -> scanning -> done | error. Хувцас бүрийн үр дүн
 * (`garments`) ирсний дараа хэрэглэгч аль хайрцгийг сонгосноор `focus` солигдоно. Хуучин хүсэлтийн
 * хариу (хэрэглэгч өөр зураг сонгосон) энд хэзээ ч ирэхгүй: component өмнөхийг abort хийдэг.
 */
export function demoReducer(state: DemoState, action: DemoAction): DemoState {
  switch (action.type) {
    case "scan":
      return { phase: "scanning", previewUrl: action.previewUrl, file: action.file };
    case "found":
      if (state.phase !== "scanning") return state;
      return { phase: "done", previewUrl: state.previewUrl, file: state.file, garments: action.garments, totalMs: action.totalMs, focus: 0 };
    case "failed":
      if (state.phase === "scanning") {
        return { phase: "error", error: action.error, previewUrl: state.previewUrl, file: state.file };
      }
      return { phase: "error", error: action.error, previewUrl: null, file: null };
    case "focus":
      if (state.phase !== "done") return state;
      return { ...state, focus: Math.max(0, Math.min(action.index, state.garments.length - 1)) };
    case "reset":
      return IDLE;
  }
}

/** 429 (хэт олон хайлт) ба сүлжээний алдааг хэрэглэгчид ойлгомжтой гурван төрөлд ангилна. */
export function classifyError(error: unknown): DemoError {
  const status = (error as { status?: number } | null)?.status;
  if (status === 429) return "rate";
  if (status === 400 || status === 413 || status === 415 || status === 422) return "unreadable";
  return "network";
}
