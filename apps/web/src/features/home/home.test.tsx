import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { recordView } from "@/features/catalog/recently-viewed";
import { makeProduct } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import { Demo } from "./demo";
import { Hero } from "./hero";
import { RecentlyViewed } from "./recently-viewed";
import { NewArrivals } from "./shelves";
import { Trending } from "./trending";

vi.mock("server-only", () => ({}));
const newest = vi.fn();
const popular = vi.fn();
const sampleProducts = vi.fn();
vi.mock("./home-data", () => ({
  newest: (...args: unknown[]) => newest(...args),
  popular: (...args: unknown[]) => popular(...args),
  sampleProducts: () => sampleProducts(),
}));
vi.mock("./live-search", () => ({
  LiveSearch: ({ samples }: { samples: { id: number; src: string }[] }) => <div data-testid="live-search" data-samples={samples.map((s) => s.src).join(",")} />,
}));

beforeEach(() => {
  newest.mockReset();
  popular.mockReset();
  sampleProducts.mockReset();
  window.localStorage.clear();
});

describe("Hero", () => {
  it("leads with a badge, the headline, one line and two ways in, with no product photos", async () => {
    const { container } = render(await Hero());

    expect(screen.getByRole("heading", { level: 1, name: "Find it from a photo." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Try it now/ })).toHaveAttribute("href", "#demo");
    expect(screen.getByRole("link", { name: "Browse new" })).toHaveAttribute("href", "/products?sort=newest");
    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens word by word without ever hiding the headline, with one accent phrase", async () => {
    const { container } = render(await Hero());

    const heading = screen.getByRole("heading", { level: 1 });
    expect([...heading.querySelectorAll(".word")].map((word) => word.textContent)).toEqual(["Find", "it", "from", "a", "photo."]);
    expect(heading.textContent).toBe("Find it from a photo.");
    expect(heading.querySelector(".text-gradient")?.textContent).toBe("from a photo.");
    expect(heading).not.toHaveClass("hero-rise");
    expect(container.querySelectorAll(".hero-rise").length).toBeGreaterThanOrEqual(3);
  });

  it("paints a gradient mesh and a grid behind the content, both hidden from assistive technology", async () => {
    const { container } = render(await Hero());

    const mesh = container.querySelector(".home-mesh");
    expect(mesh).toHaveAttribute("aria-hidden", "true");
    expect(mesh?.querySelectorAll("i")).toHaveLength(4);
    expect(container.querySelector(".home-grid")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Demo", () => {
  it("hands the live search three real catalogue photos as samples", async () => {
    sampleProducts.mockResolvedValue([1, 2, 3].map((id) => makeProduct({ id })));

    const { container } = render(await Demo());

    expect(container.querySelector("#demo")).toBe(screen.getByRole("region", { name: "Try photo search" }));
    const samples = screen.getByTestId("live-search").dataset.samples!.split(",");
    expect(samples).toHaveLength(3);
    expect(samples.every((src) => src.endsWith("_800.webp"))).toBe(true);
  });

  it("still offers the search, without samples, when the catalogue cannot be reached", async () => {
    sampleProducts.mockResolvedValue([]);

    render(await Demo());

    expect(screen.getByTestId("live-search").dataset.samples).toBe("");
  });
});

describe("Trending", () => {
  it("shows the most popular products of one department at a time, switched by tabs", async () => {
    popular.mockImplementation(async (patch: { department: string }) => [makeProduct({ id: patch.department === "women" ? 1 : patch.department === "men" ? 2 : 3, name: `${patch.department} favourite` })]);

    renderWithQuery((await Trending())!);

    expect(screen.getByRole("tab", { name: "Women", selected: true })).toBeInTheDocument();
    expect(screen.getByText("women favourite")).toBeInTheDocument();
    expect(screen.queryByText("men favourite")).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: "Men" }));

    expect(screen.getByText("men favourite")).toBeInTheDocument();
    expect(screen.queryByText("women favourite")).toBeNull();
    expect(screen.getByRole("link", { name: "Shop all →" })).toHaveAttribute("href", "/c/men?sort=popular");
  });

  it("leaves out a department with nothing popular, and the section when there is nothing at all", async () => {
    popular.mockImplementation(async (patch: { department: string }) => (patch.department === "kids" ? [makeProduct({ id: 9 })] : []));
    renderWithQuery((await Trending())!);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Kids"]);

    popular.mockResolvedValue([]);
    expect(await Trending()).toBeNull();
  });
});

describe("NewArrivals", () => {
  it("is one shelf of the newest products with a link to all of them", async () => {
    newest.mockResolvedValue([makeProduct({ id: 1, name: "Blue Kurta" })]);

    renderWithQuery((await NewArrivals())!);

    expect(screen.getByRole("link", { name: "Shop all →" })).toHaveAttribute("href", "/products?sort=newest");
    expect(screen.getByText("Blue Kurta")).toBeInTheDocument();
  });

  it("is absent when there is nothing to show", async () => {
    newest.mockResolvedValue([]);

    expect(await NewArrivals()).toBeNull();
  });
});

describe("RecentlyViewed", () => {
  it("shows nothing to a first-time visitor", () => {
    const { container } = render(<RecentlyViewed />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows what this browser looked at, newest first, and updates when another page records one", async () => {
    recordView(makeProduct({ id: 1, name: "First look", slug: "first" }));
    renderWithQuery(<RecentlyViewed />);
    expect(await screen.findByRole("heading", { name: "Recently viewed" })).toBeInTheDocument();

    recordView(makeProduct({ id: 2, name: "Second look", slug: "second" }));

    const rail = screen.getByRole("list", { name: "Recently viewed" });
    expect(await within(rail).findByText("Second look")).toBeInTheDocument();
    expect(within(rail).getAllByRole("heading").map((h) => h.textContent)).toEqual(["Second look", "First look"]);
    expect(within(rail).getByRole("link", { name: /Second look/ })).toHaveAttribute("href", "/products/2/second");
  });
});
