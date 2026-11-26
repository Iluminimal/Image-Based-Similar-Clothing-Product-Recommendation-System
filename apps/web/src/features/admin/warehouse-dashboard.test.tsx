import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FulfillmentBoard } from "@/features/admin/admin-api";
import { respond, problem, stubApi } from "@/test/api-mock";
import { signInAs } from "@/test/auth";
import { renderWithQuery } from "@/test/render";
import { WarehouseDashboard } from "./warehouse-dashboard";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/admin" }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const image = { thumb_400: "/media/t400.jpg", thumb_800: "/media/t800.jpg", blur_data_url: null };

function board(overrides: Partial<FulfillmentBoard> = {}): FulfillmentBoard {
  return {
    sla_hours: 24,
    to_ship: 3,
    overdue: 1,
    oldest_paid_at: "2026-11-24T08:00:00Z",
    shipped_today: 5,
    delivered_today: 2,
    avg_ship_hours: 6.5,
    out_of_stock: 1,
    low_stock: 2,
    low_stock_threshold: 5,
    queue: [
      {
        number: "LK-LATE0001",
        customer_name: "Болд Батбаяр",
        item_count: 2,
        shipping_method: "standard",
        paid_at: "2026-11-24T08:00:00Z",
        waiting_hours: 30,
        overdue: true,
        cancel_requested: false,
        lines: [{ name: "Blue Kurta", quantity: 2, image }],
      },
      {
        number: "LK-NEW00002",
        customer_name: "Ada Lovelace",
        item_count: 1,
        shipping_method: "pickup",
        paid_at: "2026-11-25T08:00:00Z",
        waiting_hours: 2,
        overdue: false,
        cancel_requested: false,
        lines: [{ name: "Chinos", quantity: 1, image }],
      },
    ],
    returns_expected: [],
    returns_expected_total: 0,
    stock_alerts: [
      { id: 7, name: "Slim Fit Chinos", slug: "slim-fit-chinos-7", stock_quantity: 0, committed: 0, on_hand: 0, image },
      { id: 8, name: "Blue Kurta", slug: "blue-kurta-8", stock_quantity: 2, committed: 3, on_hand: 5, image },
    ],
    my_activity: [
      {
        id: 1,
        actor_id: 1,
        actor_label: "a@b.co",
        action: "product.stock",
        entity_type: "product",
        entity_id: "7",
        data: { previous: 0, quantity: 12 },
        created_at: "2026-11-25T07:00:00Z",
      },
    ],
    ...overrides,
  };
}

beforeEach(() => signInAs("warehouse"));
afterEach(() => vi.unstubAllGlobals());

const kpi = (name: string) =>
  within(screen.getByLabelText("Warehouse figures")).getByText(name, { selector: "dt" }).closest("div")!;

describe("WarehouseDashboard", () => {
  it("shows the day's figures", async () => {
    stubApi({ "GET /api/v1/admin/fulfillment": respond(board()) });
    renderWithQuery(<WarehouseDashboard />);

    expect(await screen.findByRole("heading", { level: 1, name: "Warehouse" })).toBeInTheDocument();
    await screen.findByLabelText("Warehouse figures");
    expect(kpi("To ship")).toHaveTextContent("3");
    expect(kpi("Overdue")).toHaveTextContent("1");
    expect(kpi("Overdue")).toHaveTextContent("Waiting over 24 h");
    expect(kpi("Shipped today")).toHaveTextContent("5");
    expect(kpi("Shipped today")).toHaveTextContent("2 delivered today");
    expect(kpi("Average time to ship")).toHaveTextContent("6.5 h");
  });

  it("lists the queue longest-waiting first, marks the late order and links to ship it", async () => {
    stubApi({ "GET /api/v1/admin/fulfillment": respond(board()) });
    renderWithQuery(<WarehouseDashboard />);

    const queue = within(await screen.findByRole("region", { name: "Shipping queue" }));
    const rows = queue.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("LK-LATE0001");
    expect(rows[0]).toHaveTextContent("Overdue");
    expect(rows[0]).toHaveTextContent("30 hours");
    expect(rows[1]).not.toHaveTextContent("Overdue");
    expect(within(rows[0]!).getByRole("link", { name: /Ship/ })).toHaveAttribute("href", "/admin/orders/LK-LATE0001");
  });

  it("holds an order whose cancellation is waiting and lists the returns on their way", async () => {
    const held = { ...board().queue[0]!, cancel_requested: true };
    stubApi({
      "GET /api/v1/admin/fulfillment": respond(
        board({
          queue: [held],
          returns_expected: [
            {
              number: "LK-BACK0003",
              customer_name: "Сараа",
              item_count: 2,
              approved_at: "2026-11-25T09:00:00Z",
              lines: [{ name: "Chinos", quantity: 2, image }],
            },
          ],
          returns_expected_total: 4,
        }),
      ),
    });
    renderWithQuery(<WarehouseDashboard />);

    const [row] = within(await screen.findByRole("region", { name: "Shipping queue" })).getAllByRole("listitem");
    expect(row).toHaveTextContent("Cancellation requested");
    expect(row).not.toHaveTextContent("Overdue");
    expect(within(row!).queryByRole("link", { name: /^Ship/ })).not.toBeInTheDocument();
    expect(within(row!).getByRole("link", { name: /View\s*LK-LATE0001/ })).toBeInTheDocument();
    const returns = within(screen.getByRole("region", { name: "Returns on the way" }));
    expect(returns.getByRole("link", { name: /Receive\s*LK-BACK0003/ })).toHaveAttribute("href", "/admin/orders/LK-BACK0003");
    expect(returns.getByText("3 more not shown")).toBeInTheDocument();
  });

  it("says when nothing waits to ship and nothing runs low", async () => {
    stubApi({
      "GET /api/v1/admin/fulfillment": respond(
        board({ queue: [], stock_alerts: [], to_ship: 0, overdue: 0, avg_ship_hours: null, my_activity: [] }),
      ),
    });
    renderWithQuery(<WarehouseDashboard />);

    expect(await screen.findByText("Nothing is waiting to ship.")).toBeInTheDocument();
    expect(screen.getByText("Every product is well stocked.")).toBeInTheDocument();
    expect(screen.getByText("You haven't changed anything yet.")).toBeInTheDocument();
    expect(kpi("Average time to ship")).toHaveTextContent("–");
  });

  it("sets the stock of a product right from its alert", async () => {
    const api = stubApi({
      "GET /api/v1/admin/fulfillment": respond(board()),
      "PUT /api/v1/admin/products/7/stock": respond({}),
    });
    renderWithQuery(<WarehouseDashboard />);

    const alerts = within(await screen.findByRole("region", { name: "Stock alerts" }));
    expect(alerts.getByText("Sold out")).toBeInTheDocument();
    expect(alerts.getByText("2 left")).toBeInTheDocument();
    await userEvent.type(alerts.getByLabelText("Shelf count for Slim Fit Chinos"), "24");
    await userEvent.click(alerts.getAllByRole("button", { name: "Save" })[0]!);

    await waitFor(() => expect(api.calls.find((call) => call.method === "PUT")?.body).toEqual({ on_hand: 24 }));
  });

  it("says how many units are held for orders, so the shelf is counted correctly, and tags pickups", async () => {
    stubApi({ "GET /api/v1/admin/fulfillment": respond(board()) });
    renderWithQuery(<WarehouseDashboard />);

    const alerts = within(await screen.findByRole("region", { name: "Stock alerts" }));
    expect(alerts.getByText("3 held for orders · 5 on the shelf")).toBeInTheDocument();
    const queue = within(screen.getByRole("region", { name: "Shipping queue" }));
    const [delivery, pickup] = queue.getAllByRole("listitem");
    expect(delivery).not.toHaveTextContent("Store pickup");
    expect(pickup).toHaveTextContent("Store pickup");
  });

  it("keeps what was typed when the count is refused, so it can be corrected", async () => {
    stubApi({
      "GET /api/v1/admin/fulfillment": respond(board()),
      "PUT /api/v1/admin/products/8/stock": () =>
        problem(409, "Below committed", { type: "urn:angel:problem:stock-below-committed", committed: 3 }),
    });
    renderWithQuery(<WarehouseDashboard />);

    const alerts = within(await screen.findByRole("region", { name: "Stock alerts" }));
    const field = alerts.getByLabelText("Shelf count for Blue Kurta");
    await userEvent.type(field, "1");
    await userEvent.click(alerts.getAllByRole("button", { name: "Save" })[1]!);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("3 are held for orders that haven't shipped, so the shelf count can't be lower than that."),
    );
    expect(field).toHaveValue(1);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("does not save an empty or impossible number", async () => {
    const api = stubApi({ "GET /api/v1/admin/fulfillment": respond(board()) });
    renderWithQuery(<WarehouseDashboard />);

    const alerts = within(await screen.findByRole("region", { name: "Stock alerts" }));
    expect(alerts.getAllByRole("button", { name: "Save" })[0]).toBeDisabled();
    await userEvent.type(alerts.getByLabelText("Shelf count for Slim Fit Chinos"), "-3");
    await userEvent.click(alerts.getAllByRole("button", { name: "Save" })[0]!);

    expect(api.calls.filter((call) => call.method === "PUT")).toHaveLength(0);
  });

  it("describes the worker's own recent actions", async () => {
    stubApi({ "GET /api/v1/admin/fulfillment": respond(board()) });
    renderWithQuery(<WarehouseDashboard />);

    const mine = within(await screen.findByRole("region", { name: "My recent activity" }));
    expect(mine.getByText("Set stock")).toBeInTheDocument();
    expect(mine.getByText("0 → 12")).toBeInTheDocument();
    expect(mine.getByRole("link", { name: "Product #7" })).toHaveAttribute("href", "/admin/products/7");
  });

  it("reports a failure and can try again", async () => {
    stubApi({ "GET /api/v1/admin/fulfillment": problem(500, "Boom") });
    renderWithQuery(<WarehouseDashboard />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
