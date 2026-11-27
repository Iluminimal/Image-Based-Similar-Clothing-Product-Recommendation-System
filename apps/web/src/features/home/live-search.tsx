"use client";

import {
  Camera,
  ImagePlus,
  Loader2,
  RotateCcw,
  SearchX,
  ShieldCheck,
} from "lucide-react";
import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type CSSProperties,
  type DragEvent,
} from "react";
import {
  ProductCard,
  ProductCardSkeleton,
} from "@/components/product/product-card";
import { Button } from "@/components/ui/button";
import { emptyFilters } from "@/features/catalog/filters";
import { DottedFrame } from "@/features/search/dotted-frame";
import { stackOrder } from "@/features/search/region-overlay";
import { SimilarityBadge } from "@/features/search/similarity-badge";
import { useSearchStore } from "@/features/search/search-store";
import { firstImage, usePasteImage } from "@/features/search/use-image-input";
import { cn } from "@/lib/utils";
import {
  classifyError,
  demoReducer,
  IDLE,
  type DemoError,
} from "./live-search-state";

// Камерын dialog-ыг хэрэглэгч хүсэх үед л ачаална.
const CameraDialog = dynamic(
  () => import("@/features/search/camera-dialog").then((m) => m.CameraDialog),
  { ssr: false },
);

const ACCEPT =
  "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";
const RESULTS = 4;

export type DemoSample = { id: number; name: string; src: string };

/**
 * Нүүр хуудасны гол хэсэг: хуудсан дээрээ ажилладаг зургаар хайлт. Зураг оруулах (чирэх, сонгох, paste,
 * камер) эсвэл жишээ сонгоход /search/garments дуудна. Олдсон хувцас бүрт дугаартай хүрээ зурж, баруун талд
 * төстэй бодит бараануудыг харуулна. Хайлтын код (`search-api`, `normalize-image`) анх ашиглахад л
 * ачаалагддаг тул хуудас хөнгөн нээгдэнэ. Зургийг хэзээ ч хадгалахгүй: зөвхөн энэ browser-ийн санах ойд
 * байна.
 */
export function LiveSearch({ samples }: { samples: DemoSample[] }) {
  const t = useTranslations("home.demo");
  const router = useRouter();
  const [state, dispatch] = useReducer(demoReducer, IDLE);
  const fileInput = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const [dragging, setDragging] = useState(false);
  const [cameraRequested, setCameraRequested] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);

  // Preview-ийн Object URL-ыг зураг солигдох, component unmount хийгдэх бүрд чөлөөлнө.
  const previewUrl = state.phase === "idle" ? null : state.previewUrl;
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );
  useEffect(() => () => abort.current?.abort(), []);

  const run = useCallback(async (blob: Blob & { name?: string }) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    let file: File;
    try {
      const { normalizeImage } =
        await import("@/features/search/normalize-image");
      file = await normalizeImage(blob);
    } catch {
      if (!controller.signal.aborted)
        dispatch({ type: "failed", error: "unreadable" });
      return;
    }
    if (controller.signal.aborted) return;
    dispatch({ type: "scan", previewUrl: URL.createObjectURL(file), file });
    try {
      const { searchGarments } = await import("@/features/search/search-api");
      const response = await searchGarments(
        file,
        { filters: emptyFilters(), limit: RESULTS },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      dispatch({
        type: "found",
        garments: response.garments,
        totalMs: Math.round(response.timings.total_ms),
      });
    } catch (cause) {
      if (
        controller.signal.aborted ||
        (cause instanceof DOMException && cause.name === "AbortError")
      )
        return;
      dispatch({ type: "failed", error: classifyError(cause) });
    }
  }, []);

  usePasteImage((file) => void run(file), true);

  async function trySample(sample: DemoSample) {
    try {
      const response = await fetch(sample.src);
      if (!response.ok) throw new Error(String(response.status));
      await run(await response.blob());
    } catch {
      dispatch({ type: "failed", error: "network" });
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = firstImage(event.dataTransfer.files);
    if (file) void run(file);
  }

  function seeAll() {
    if (state.phase !== "done") return;
    const store = useSearchStore.getState();
    store.setImage(state.file);
    if (state.garments.length > 1 && state.focus > 0)
      store.focusRegion(state.focus);
    router.push("/search");
  }

  function openCamera() {
    setCameraRequested(true);
    setCameraOpen(true);
  }

  const done = state.phase === "done" ? state : null;
  const garment = done?.garments[done.focus];
  const busy = state.phase === "scanning";
  // Зураг сонгохоос өмнө үр дүнгийн хэсэг хоосон тул нэг баганаар харуулна.
  const split = state.phase !== "idle";

  return (
    <div
      className="home-window hero-rise"
      style={{ "--d": "520ms" } as CSSProperties}
      data-phase={state.phase}
    >
      <div className="home-window-bar" aria-hidden>
        <i />
        <i />
        <i />
        <span>{t("windowTitle")}</span>
      </div>

      <div
        className={cn(
          "grid gap-0",
          split && "lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]",
        )}
      >
        {/* Зургийн хэсэг */}
        <div
          className={cn(
            "border-border flex flex-col gap-4 p-4 sm:p-6",
            split
              ? "border-b lg:border-r lg:border-b-0"
              : "mx-auto w-full max-w-2xl",
          )}
        >
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "home-stage relative flex items-center justify-center overflow-hidden rounded-2xl",
              split ? "h-[22rem] lg:h-[28rem]" : "h-[18rem] lg:h-[20rem]",
              state.phase === "idle" || state.phase === "error"
                ? "home-stage-empty"
                : "home-stage-photo",
              dragging && "home-stage-drag",
            )}
          >
            {previewUrl ? (
              <div className="relative inline-block max-h-full max-w-full">
                {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL, next/image cannot optimise it */}
                <img
                  src={previewUrl}
                  alt=""
                  className="block max-h-[22rem] w-auto max-w-full rounded-lg object-contain lg:max-h-[28rem]"
                />
                {busy && <div aria-hidden className="home-scan" />}
                {done && (
                  <Frames
                    garments={done.garments}
                    focus={done.focus}
                    onFocus={(index) => dispatch({ type: "focus", index })}
                    label={(n) => t("item", { number: n })}
                    group={t("detected")}
                  />
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-4 px-6 text-center">
                <span aria-hidden className="home-stage-icon">
                  <ImagePlus className="size-6" />
                </span>
                <div>
                  <p className="font-semibold">{t("drop")}</p>
                  <p className="text-muted-foreground type-caption mt-1">
                    {t("dropHint")}
                  </p>
                </div>
                <div className="flex flex-wrap justify-center gap-2">
                  <Button size="lg" onClick={() => fileInput.current?.click()}>
                    <ImagePlus aria-hidden /> {t("choose")}
                  </Button>
                  <Button size="lg" variant="bordered" onClick={openCamera}>
                    <Camera aria-hidden /> {t("camera")}
                  </Button>
                </div>
              </div>
            )}
            {busy && (
              <p
                role="status"
                className="home-chip absolute bottom-3 left-1/2 -translate-x-1/2"
              >
                <Loader2 aria-hidden className="size-3.5 animate-spin" />{" "}
                {t("scanning")}
              </p>
            )}
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPT}
              className="sr-only"
              tabIndex={-1}
              aria-label={t("choose")}
              data-testid="demo-file"
              onChange={(event) => {
                const file = firstImage(event.target.files);
                event.target.value = "";
                if (file) void run(file);
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="text-muted-foreground type-fine">
              {t("samples")}
            </span>
            <ul className="flex gap-2">
              {samples.map((sample, index) => (
                <li key={sample.id}>
                  <button
                    type="button"
                    aria-label={t("sample", { number: index + 1 })}
                    disabled={busy}
                    onClick={() => void trySample(sample)}
                    className="home-sample focus-visible:ring-ring/50 outline-none focus-visible:ring-3"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- tiny same-origin thumbnail, already 400/800 px WebP */}
                    <img
                      src={sample.src}
                      alt=""
                      width={48}
                      height={64}
                      loading="lazy"
                      decoding="async"
                    />
                  </button>
                </li>
              ))}
            </ul>
            {(state.phase === "done" || state.phase === "error") && (
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => dispatch({ type: "reset" })}
              >
                <RotateCcw aria-hidden /> {t("another")}
              </Button>
            )}
          </div>
          {!split && (
            <p className="text-muted-foreground type-fine inline-flex items-center justify-center gap-1.5">
              <ShieldCheck aria-hidden className="size-3.5" /> {t("private")}
            </p>
          )}
        </div>

        {/* Үр дүн */}
        {split && (
          <div className="flex min-h-[24rem] flex-col gap-4 p-4 sm:p-6 lg:min-h-[32rem]">
            {state.phase === "error" ? (
              <Problem
                error={state.error}
                onRetry={() =>
                  state.file
                    ? void run(state.file)
                    : dispatch({ type: "reset" })
                }
                canRetry={state.file !== null}
              />
            ) : done && garment ? (
              <>
                <div className="flex items-center justify-between gap-3">
                  <p className="type-caption font-medium">
                    {done.garments.length > 1
                      ? t("itemOf", {
                          number: garment.index + 1,
                          total: done.garments.length,
                        })
                      : t("similar")}
                  </p>
                  <p className="home-chip" aria-live="polite">
                    <span aria-hidden className="home-dot" />{" "}
                    {t("found", { ms: done.totalMs })}
                  </p>
                </div>
                {garment.results.length === 0 ? (
                  <div className="tile flex flex-1 items-center justify-center gap-3 px-5 py-10">
                    <SearchX
                      aria-hidden
                      className="text-muted-foreground size-5 shrink-0"
                    />
                    <p className="text-muted-foreground type-caption">
                      {t("none")}
                    </p>
                  </div>
                ) : (
                  <ul className="grid flex-1 grid-cols-2 content-start gap-3 md:grid-cols-4">
                    {garment.results.slice(0, RESULTS).map((hit, i) => (
                      <li
                        key={hit.product.id}
                        className="home-result"
                        style={{ "--i": i } as CSSProperties}
                      >
                        <ProductCard
                          product={hit.product}
                          headingLevel={3}
                          sizes="(min-width: 1024px) 14vw, (min-width: 768px) 22vw, 45vw"
                          badge={
                            <SimilarityBadge similarity={hit.similarity} />
                          }
                        />
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-muted-foreground type-fine inline-flex items-center gap-1.5">
                    <ShieldCheck aria-hidden className="size-3.5" />{" "}
                    {t("private")}
                  </p>
                  <Button onClick={seeAll}>{t("seeAll")}</Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-muted-foreground type-caption">
                  {t("scanning")}
                </p>
                <ul
                  aria-hidden
                  className="grid flex-1 grid-cols-2 content-start gap-3 md:grid-cols-4"
                >
                  {Array.from({ length: RESULTS }, (_, i) => (
                    <li key={i}>
                      <ProductCardSkeleton />
                    </li>
                  ))}
                </ul>
                <p className="text-muted-foreground type-fine inline-flex items-center gap-1.5">
                  <ShieldCheck aria-hidden className="size-3.5" />{" "}
                  {t("private")}
                </p>
              </>
            )}
          </div>
        )}
      </div>

      {cameraRequested && (
        <CameraDialog
          open={cameraOpen}
          onOpenChange={setCameraOpen}
          onCapture={(file) => {
            setCameraOpen(false);
            void run(file);
          }}
        />
      )}
    </div>
  );
}

function Frames({
  garments,
  focus,
  onFocus,
  label,
  group,
}: {
  garments: {
    index: number;
    region: { box: { x: number; y: number; width: number; height: number } };
  }[];
  focus: number;
  onFocus: (index: number) => void;
  label: (number: number) => string;
  group: string;
}) {
  const order = stackOrder(
    garments.map((g) => ({ ...g.region, label: null, score: 1 })),
  );
  return (
    <div
      role="group"
      aria-label={group}
      className="pointer-events-none absolute inset-0"
    >
      {garments.map((garment, i) => {
        const { x, y, width, height } = garment.region.box;
        const active = i === focus;
        return (
          <button
            key={garment.index}
            type="button"
            aria-pressed={active}
            aria-label={label(garment.index + 1)}
            onClick={() => onFocus(i)}
            style={{
              left: `${x * 100}%`,
              top: `${y * 100}%`,
              width: `${width * 100}%`,
              height: `${height * 100}%`,
              zIndex: 10 + order[i]!,
            }}
            className={cn(
              "home-frame group pointer-events-auto absolute rounded-2xl outline-none",
              active && "home-frame-active",
            )}
          >
            <DottedFrame tone={active ? "brand" : "white"} />
            <span aria-hidden className="home-frame-badge">
              {garment.index + 1}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Problem({
  error,
  onRetry,
  canRetry,
}: {
  error: DemoError;
  onRetry: () => void;
  canRetry: boolean;
}) {
  const t = useTranslations("home.demo.errors");
  return (
    <div
      role="alert"
      className="tile flex flex-1 flex-col items-center justify-center gap-4 px-6 py-10 text-center"
    >
      <SearchX aria-hidden className="text-muted-foreground size-6" />
      <p className="type-caption max-w-xs">{t(error)}</p>
      {canRetry && error !== "unreadable" && (
        <Button variant="bordered" size="lg" onClick={onRetry}>
          <RotateCcw aria-hidden /> {t("retry")}
        </Button>
      )}
    </div>
  );
}
