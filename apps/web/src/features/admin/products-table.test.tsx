import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "@/features/auth/auth-store";
import { signInAs } from "@/test/auth";
import { json, stubApi } from "@/test/api-mock";
import { makeAdminProduct } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import type { ProductListParams } from "./admin-api";
import { ProductsTable } from "./products-table";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/products",
}));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const params: ProductListParams = { q: "", status: "all", stock: "all", sort: "newest", page: 1 };
const onSale = makeAdminProduct({ id: 7, name: "Linen camp shirt", price_cents: 4999 });
const withdrawn = makeAdminProduct({ id: 8, name: "Wool coat", is_active: false, stock_quantity: 0 });
const page = (items = [onSale, withdrawn]) => ({
  items,
  status_counts: {
    all: items.length,
    active: items.filter((p) => p.is_active).length,
    inactive: items.filter((p) => !p.is_active).length,
  },
  total: items.length,
  page: 1,
  page_size: 25,
  pages: 1,
});

beforeEach(() => {
  replace.mockClear();
  toast.success.mockClear();
  toast.error.mockClear();
  signInAs("warehouse");
});
afterEach(() => vi.unstubAllGlobals());

describe("ProductsTable", () => {
  it("lists products with price, stock and status", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={params} />);

    const table = await screen.findByRole("table", { name: "Products" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Linen camp shirt");
    expect(rows[0]).toHaveTextContent("$49.99");
    expect(rows[0]).toHaveTextContent("On sale");
    expect(rows[1]).toHaveTextContent("Not selling");
    expect(within(rows[0]!).getByRole("switch", { name: "Sell Linen camp shirt" })).toBeChecked();
    expect(within(rows[1]!).getByRole("switch", { name: "Sell Wool coat" })).not.toBeChecked();
  });

  it("asks the API for the filters in the URL", async () => {
    const api = stubApi({ "GET /api/v1/admin/products": { body: page([]) } });
    renderWithQuery(<ProductsTable params={{ q: "shirt", status: "inactive", stock: "all", sort: "price_asc", page: 3 }} />);

    await screen.findByText("No products found");
    const search = new URLSearchParams(api.calls[0]!.search);
    expect(Object.fromEntries(search)).toMatchObject({ q: "shirt", status: "inactive", sort: "price_asc", page: "3" });
    expect(api.calls[0]!.headers.get("authorization")).toBe("Bearer t");
  });

  it("filters by status with tabs that count each status and start at the first page", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={{ ...params, status: "inactive", page: 2 }} />);
    await screen.findByRole("table");

    const tabs = within(screen.getByRole("navigation", { name: "Filter by status" }));
    expect(tabs.getByRole("link", { name: "All 2" })).toHaveAttribute("href", "/admin/products");
    expect(tabs.getByRole("link", { name: "On sale 1" })).toHaveAttribute("href", "/admin/products?status=active");
    expect(tabs.getByRole("link", { name: "Not selling 1" })).toHaveAttribute("aria-current", "page");
  });

  it("searches when the form is submitted", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={params} />);
    await screen.findByRole("table");

    await userEvent.type(screen.getByLabelText("Search by name or id"), "camp shirt{enter}");

    expect(replace).toHaveBeenCalledWith("/admin/products?q=camp+shirt");
  });

  it("stops selling with one tap, keeps the row and the counts in step, and offers to undo", async () => {
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page() },
      "POST /api/v1/admin/products/7/deactivate": { body: { ...onSale, is_active: false } },
      "POST /api/v1/admin/products/7/activate": { body: onSale },
    });
    renderWithQuery(<ProductsTable params={{ ...params, status: "active" }} />);
    const toggle = await screen.findByRole("switch", { name: "Sell Linen camp shirt" });
    expect(toggle).toBeChecked();

    await userEvent.click(toggle);

    await waitFor(() => expect(api.count("POST /api/v1/admin/products/7/deactivate")).toBe(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).not.toBeChecked();
    expect(screen.getByRole("link", { name: "On sale 0" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Not selling 2" })).toBeInTheDocument();
    // "On sale" таб дээр ч мөр үлдэнэ: жагсаалтыг дахин татахгүй.
    expect(screen.getByRole("switch", { name: "Sell Linen camp shirt" })).toBeInTheDocument();
    expect(api.count("GET /api/v1/admin/products")).toBe(1);

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const [message, options] = toast.success.mock.calls[0]!;
    expect(message).toBe("“Linen camp shirt” is no longer on sale.");
    expect(options.action.label).toBe("Undo");
    act(() => options.action.onClick());

    await waitFor(() => expect(api.count("POST /api/v1/admin/products/7/activate")).toBe(1));
    await waitFor(() => expect(toggle).toBeChecked());
    // Буцаасны дараа дахин "буцаах" санал болгохгүй.
    expect(toast.success.mock.calls.at(-1)![1]?.action).toBeUndefined();
  });

  it("puts the switch back and says why when the change is refused", async () => {
    stubApi({
      "GET /api/v1/admin/products": { body: page() },
      "POST /api/v1/admin/products/8/activate": () => json({ title: "Forbidden", status: 403 }, 403),
    });
    renderWithQuery(<ProductsTable params={params} />);
    const toggle = await screen.findByRole("switch", { name: "Sell Wool coat" });

    await userEvent.click(toggle);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toggle).not.toBeChecked();
    expect(screen.getByRole("link", { name: "Not selling 1" })).toBeInTheDocument();
  });

  it("mentions units already ordered when selling stops", async () => {
    const held = makeAdminProduct({ id: 7, name: "Linen camp shirt", committed: 2, ordered: true });
    stubApi({
      "GET /api/v1/admin/products": { body: page([held]) },
      "POST /api/v1/admin/products/7/deactivate": { body: { ...held, is_active: false } },
    });
    renderWithQuery(<ProductsTable params={params} />);

    await userEvent.click(await screen.findByRole("switch", { name: "Sell Linen camp shirt" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success.mock.calls[0]![1].description).toBe("Orders already placed for 2 units are not affected.");
  });

  it("warns when a product on sale has nothing left to sell", async () => {
    const empty = makeAdminProduct({ id: 7, name: "Linen camp shirt", stock_quantity: 0 });
    stubApi({ "GET /api/v1/admin/products": { body: page([empty, withdrawn]) } });
    renderWithQuery(<ProductsTable params={params} />);

    const rows = within(await screen.findByRole("table")).getAllByRole("row").slice(1);

    expect(rows[0]).toHaveTextContent("Out of stock, so it can't be bought");
    expect(rows[1]).not.toHaveTextContent("can't be bought"); // зарахаа больсонд анхааруулга хэрэггүй
  });

  async function openMenu(name: string, item: string) {
    await userEvent.click(await screen.findByRole("button", { name: `More actions for ${name}` }));
    await userEvent.click(await screen.findByRole("menuitem", { name: item }));
  }

  it("deletes a product nobody ordered, only after confirmation", async () => {
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page() },
      "DELETE /api/v1/admin/products/7": () => new Response(null, { status: 204 }),
    });
    renderWithQuery(<ProductsTable params={params} />);

    await openMenu("Linen camp shirt", "Delete");
    let dialog = await screen.findByRole("dialog", { name: "Delete this product?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(api.count("DELETE /api/v1/admin/products/7")).toBe(0);

    await openMenu("Linen camp shirt", "Delete");
    dialog = await screen.findByRole("dialog", { name: "Delete this product?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.count("DELETE /api/v1/admin/products/7")).toBe(1));
    await waitFor(() => expect(api.count("GET /api/v1/admin/products")).toBe(2));
  });

  it("explains why an ordered product stays, and offers to stop selling it", async () => {
    const ordered = makeAdminProduct({ id: 7, name: "Linen camp shirt", ordered: true });
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page([ordered]) },
      "POST /api/v1/admin/products/7/deactivate": { body: { ...ordered, is_active: false } },
    });
    renderWithQuery(<ProductsTable params={params} />);

    await openMenu("Linen camp shirt", "Delete");
    const dialog = await screen.findByRole("dialog", { name: "This product can't be deleted" });
    expect(within(dialog).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Stop selling" }));

    await waitFor(() => expect(api.count("POST /api/v1/admin/products/7/deactivate")).toBe(1));
  });

  it("changes the price from the list without sending an uncounted shelf", async () => {
    const priced = makeAdminProduct({ id: 7, name: "Linen camp shirt", price_cents: 8_790_000, on_hand: 12 });
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page([priced]) },
      "PATCH /api/v1/admin/products/7": { body: priced },
    });
    renderWithQuery(<ProductsTable params={params} />);

    await openMenu("Linen camp shirt", "Price and stock");
    const dialog = await screen.findByRole("dialog", { name: "Price and stock" });
    const price = within(dialog).getByLabelText("Price (₮)");
    expect(price).toHaveValue("87900");
    expect(within(dialog).getByLabelText("On the shelf")).toHaveValue("12");
    await userEvent.clear(price);
    await userEvent.type(price, "76500{enter}");

    await waitFor(() => expect(api.count("PATCH /api/v1/admin/products/7")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")!.body).toEqual({ price_cents: 7_650_000 });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("sends the shelf count once it has been counted, and refuses a wrong price", async () => {
    const priced = makeAdminProduct({ id: 7, name: "Linen camp shirt", price_cents: 8_790_000, on_hand: 12 });
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page([priced]) },
      "PATCH /api/v1/admin/products/7": { body: priced },
    });
    renderWithQuery(<ProductsTable params={params} />);

    await openMenu("Linen camp shirt", "Price and stock");
    const dialog = await screen.findByRole("dialog");
    const price = within(dialog).getByLabelText("Price (₮)");
    await userEvent.clear(price);
    await userEvent.type(price, "87,900{enter}");
    expect(await within(dialog).findByText(/whole tugrik/i)).toBeInTheDocument();
    expect(api.count("PATCH /api/v1/admin/products/7")).toBe(0);

    await userEvent.clear(price);
    await userEvent.type(price, "87900"); // анхны утга руугаа буцсан
    const shelf = within(dialog).getByLabelText("On the shelf");
    await userEvent.clear(shelf);
    await userEvent.type(shelf, "9{enter}");

    await waitFor(() => expect(api.count("PATCH /api/v1/admin/products/7")).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")!.body).toEqual({ on_hand: 9 });
  });

  it("says why the list failed and can retry", async () => {
    let attempts = 0;
    stubApi({
      "GET /api/v1/admin/products": () => {
        attempts += 1;
        return attempts === 1 ? json({ title: "Forbidden", status: 403 }, 403) : { body: page() };
      },
    });
    renderWithQuery(<ProductsTable params={params} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("isn't allowed");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("makes the price and stock headers sort links and says the current order", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={{ ...params, sort: "price_asc" }} />);

    const table = await screen.findByRole("table", { name: "Products" });
    expect(within(table).getByRole("columnheader", { name: /Price/ })).toHaveAttribute("aria-sort", "ascending");
    expect(within(table).getByRole("link", { name: "Price" })).toHaveAttribute("href", "/admin/products?sort=price_desc");
    expect(within(table).getByRole("link", { name: "Stock" })).toHaveAttribute("href", "/admin/products?sort=stock_asc");
  });

  it("stops selling several at once after confirmation, saying how many change, and can undo", async () => {
    const other = makeAdminProduct({ id: 9, name: "Denim jacket" });
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page([onSale, withdrawn, other]) },
      "POST /api/v1/admin/products/7/deactivate": { body: { ...onSale, is_active: false } },
      "POST /api/v1/admin/products/9/deactivate": { body: { ...other, is_active: false } },
      "POST /api/v1/admin/products/7/activate": { body: onSale },
      "POST /api/v1/admin/products/9/activate": { body: other },
    });
    renderWithQuery(<ProductsTable params={params} />);

    for (const name of ["Linen camp shirt", "Wool coat", "Denim jacket"]) {
      await userEvent.click(await screen.findByRole("checkbox", { name: `Select ${name}` }));
    }
    const bar = within(screen.getByRole("region", { name: "3 selected" }));
    expect(bar.getByRole("button", { name: "Put on sale (1)" })).toBeInTheDocument();
    await userEvent.click(bar.getByRole("button", { name: "Stop selling (2)" }));
    const dialog = await screen.findByRole("dialog", { name: "Stop selling 2 products?" });
    expect(api.count("POST /api/v1/admin/products/7/deactivate")).toBe(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Stop selling" }));

    await waitFor(() => expect(api.count("POST /api/v1/admin/products/9/deactivate")).toBe(1));
    await waitFor(() => expect(screen.queryByRole("region", { name: /selected/ })).not.toBeInTheDocument());
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    act(() => toast.success.mock.calls.at(-1)![1].action.onClick());

    // Зөвхөн өөрчлөгдсөн хоёр нь буцна: анхнаасаа зарахаа больсон бараа хэвээр.
    await waitFor(() => expect(api.count("POST /api/v1/admin/products/9/activate")).toBe(1));
    expect(api.count("POST /api/v1/admin/products/7/activate")).toBe(1);
    expect(api.count("POST /api/v1/admin/products/8/activate")).toBe(0);
  });

  it("deletes the selected products it can and says which stay", async () => {
    const ordered = makeAdminProduct({ id: 9, name: "Denim jacket", ordered: true });
    const api = stubApi({
      "GET /api/v1/admin/products": { body: page([onSale, ordered]) },
      "DELETE /api/v1/admin/products/7": () => new Response(null, { status: 204 }),
    });
    renderWithQuery(<ProductsTable params={params} />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "Select Linen camp shirt" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Denim jacket" }));
    await userEvent.click(within(screen.getByRole("region", { name: "2 selected" })).getByRole("button", { name: "Delete (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete 1 product?" });
    expect(dialog).toHaveTextContent("1 selected product is in past orders and will be kept.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.count("DELETE /api/v1/admin/products/7")).toBe(1));
    expect(api.count("DELETE /api/v1/admin/products/9")).toBe(0);
  });

  it("switches to a photo grid and keeps the selection controls", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={params} />);
    await screen.findByRole("table", { name: "Products" });

    await userEvent.click(screen.getByRole("button", { name: "Grid" }));

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const grid = screen.getByRole("list", { name: "Products" });
    expect(within(grid).getAllByRole("listitem")).toHaveLength(2);
    expect(within(grid).getByRole("checkbox", { name: "Select Wool coat" })).toBeInTheDocument();
    expect(within(grid).getByText("Sold out")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Table" }));
  });

  it("lets an administrator look at products but not add, withdraw, restore or select them", async () => {
    signInAs("admin");
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={params} />);

    const table = await screen.findByRole("table", { name: "Products" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(table).queryByRole("switch")).not.toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: /More actions/ })).not.toBeInTheDocument();
    expect(table).toHaveTextContent("Not selling");
    expect(screen.queryByRole("link", { name: "New product" })).not.toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "View Linen camp shirt" })).toHaveAttribute("href", "/admin/products/7");
  });

  it("offers a warehouse worker the new product link", async () => {
    stubApi({ "GET /api/v1/admin/products": { body: page() } });
    renderWithQuery(<ProductsTable params={params} />);

    await screen.findByRole("table", { name: "Products" });
    expect(screen.getByRole("link", { name: /New product/ })).toHaveAttribute("href", "/admin/products/new");
  });

  it("does not ask the API anything for a customer", () => {
    useAuth.setState({ user: { id: 1, email: "a@b.co", full_name: "Ada", role: "customer", avatar_url: null, has_password: true, phone: null, email_verified: false, phone_verified: false, providers: [] as string[] } });
    const api = stubApi({});
    renderWithQuery(<ProductsTable params={params} />);

    expect(api.calls).toHaveLength(0);
  });
});
