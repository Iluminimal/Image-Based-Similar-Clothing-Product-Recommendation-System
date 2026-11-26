import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { useSearchStore } from "@/features/search/search-store";
import { makeGarmentResponse, makeProduct } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import { LiveSearch } from "./live-search";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));
const searchGarments = vi.fn();
vi.mock("@/features/search/search-api", () => ({ searchGarments: (...args: unknown[]) => searchGarments(...args) }));
vi.mock("@/features/search/normalize-image", () => ({
  normalizeImage: async (blob: Blob) => new File([blob], "photo.jpg", { type: "image/jpeg" }),
}));
vi.mock("@/features/search/camera-dialog", () => ({ CameraDialog: () => null }));

const SAMPLES = [
  { id: 1, name: "Dress", src: "/media/products/001/1_800.webp" },
  { id: 2, name: "Shirt", src: "/media/products/001/2_800.webp" },
  { id: 3, name: "Sandal", src: "/media/products/001/3_800.webp" },
];
const photo = () => new File(["jpeg"], "look.jpg", { type: "image/jpeg" });

const TWO = makeGarmentResponse([
  { box: { x: 0.2, y: 0.1, width: 0.5, height: 0.3 }, products: [makeProduct({ id: 10, name: "Top match" })] },
  { box: { x: 0.25, y: 0.5, width: 0.4, height: 0.4 }, products: [makeProduct({ id: 20, name: "Skirt match" })] },
]);

beforeEach(() => {
  push.mockReset();
  searchGarments.mockReset();
  useSearchStore.getState().clearImage();
  let n = 0;
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => `blob:photo-${++n}`, revokeObjectURL: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());

function setup() {
  return renderWithQuery(<LiveSearch samples={SAMPLES} />);
}
async function choose(file = photo()) {
  await userEvent.upload(screen.getByTestId("demo-file"), file);
}

describe("LiveSearch", () => {
  it("starts as a single-column drop zone with three samples and a privacy note, and no empty results pane", () => {
    const { container } = setup();

    expect(screen.getByText("Drop a photo here")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose photo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Camera" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Sample \d$/ })).toHaveLength(3);
    expect(screen.queryByText("Similar items appear here.")).not.toBeInTheDocument();
    expect(container.querySelector("ul[aria-hidden]")).toBeNull();
    expect(screen.getByText("Photos are never stored.")).toBeInTheDocument();
    expect(searchGarments).not.toHaveBeenCalled();
  });

  it("searches a chosen photo for garments and shows real matches with the time it took", async () => {
    searchGarments.mockResolvedValue(makeGarmentResponse([{ products: [makeProduct({ id: 10, name: "Blue Kurta" })] }]));
    setup();

    await choose();

    expect(await screen.findByText("Blue Kurta")).toBeInTheDocument();
    expect(screen.getByText("Found in 90 ms")).toBeInTheDocument();
    expect(searchGarments).toHaveBeenCalledTimes(1);
    expect(searchGarments.mock.calls[0]![0]).toBeInstanceOf(File);
    expect(searchGarments.mock.calls[0]![1]).toMatchObject({ limit: 4 });
  });

  it("outlines every garment it found where it found it, and switches the matches when another one is picked", async () => {
    searchGarments.mockResolvedValue(TWO);
    setup();

    await choose();

    const group = await screen.findByRole("group", { name: "Detected items" });
    const [first, second] = within(group).getAllByRole("button");
    expect(first).toHaveAttribute("aria-label", "Item 1");
    expect(first).toHaveStyle({ left: "20%", top: "10%", width: "50%", height: "30%" });
    expect(second).toHaveStyle({ left: "25%", top: "50%" });
    expect(first).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Top match")).toBeInTheDocument();
    expect(screen.getByText("Item 1 of 2")).toBeInTheDocument();

    await userEvent.click(second!);

    expect(second).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Skirt match")).toBeInTheDocument();
    expect(screen.queryByText("Top match")).toBeNull();
  });

  it("tries a sample photo: fetches the catalogue image and searches it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["img"], { type: "image/webp" }))));
    searchGarments.mockResolvedValue(makeGarmentResponse([{ products: [makeProduct({ id: 30, name: "Sample match" })] }]));
    setup();

    await userEvent.click(screen.getByRole("button", { name: "Sample 2" }));

    expect(await screen.findByText("Sample match")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/media/products/001/2_800.webp");
  });

  it("says so when no similar item exists", async () => {
    searchGarments.mockResolvedValue(makeGarmentResponse([{ products: [] }]));
    setup();

    await choose();

    expect(await screen.findByText("No similar items found. Try another photo.")).toBeInTheDocument();
  });

  it("explains a rate limit, and lets the visitor retry the same photo", async () => {
    searchGarments.mockRejectedValueOnce(new ApiError({ status: 429, title: "Too many requests" }));
    searchGarments.mockResolvedValueOnce(makeGarmentResponse([{ products: [makeProduct({ id: 40, name: "Second try" })] }]));
    setup();

    await choose();

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many searches in a short time");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Second try")).toBeInTheDocument();
    expect(searchGarments).toHaveBeenCalledTimes(2);
  });

  it("reports a network failure and a photo that cannot be read, without leaving the page", async () => {
    searchGarments.mockRejectedValueOnce(new TypeError("fetch failed"));
    setup();

    await choose();
    expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach search");

    searchGarments.mockRejectedValueOnce(new ApiError({ status: 422, title: "Unprocessable" }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("couldn't read that photo"));
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("hands the photo and the picked garment to the full search page", async () => {
    searchGarments.mockResolvedValue(TWO);
    setup();
    await choose();
    await userEvent.click(within(await screen.findByRole("group", { name: "Detected items" })).getByRole("button", { name: "Item 2" }));

    await userEvent.click(screen.getByRole("button", { name: "See all results" }));

    expect(push).toHaveBeenCalledWith("/search");
    const state = useSearchStore.getState();
    expect(state.image?.file).toBeInstanceOf(File);
    expect(state.regionIndex).toBe(1);
    expect(state.focused).toBe(true);
  });

  it("starts over with another photo", async () => {
    searchGarments.mockResolvedValue(TWO);
    setup();
    await choose();
    await screen.findByText("Top match");

    await userEvent.click(screen.getByRole("button", { name: "Try another" }));

    expect(screen.getByText("Drop a photo here")).toBeInTheDocument();
    expect(screen.queryByText("Top match")).toBeNull();
  });

  it("ignores the answer to a photo that was replaced while it was still being searched", async () => {
    let finishFirst: (value: unknown) => void = () => {};
    searchGarments.mockImplementationOnce(
      (_file: File, _params: unknown, signal: AbortSignal) =>
        new Promise((resolve, reject) => {
          finishFirst = resolve;
          signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    searchGarments.mockResolvedValueOnce(makeGarmentResponse([{ products: [makeProduct({ id: 50, name: "Newer photo" })] }]));
    setup();

    await choose(photo());
    await screen.findByText("Finding matches…", { selector: "p[role=status]" });
    await choose(photo());

    expect(await screen.findByText("Newer photo")).toBeInTheDocument();
    act(() => finishFirst(makeGarmentResponse([{ products: [makeProduct({ id: 51, name: "Stale photo" })] }])));
    expect(screen.queryByText("Stale photo")).toBeNull();
  });
});
