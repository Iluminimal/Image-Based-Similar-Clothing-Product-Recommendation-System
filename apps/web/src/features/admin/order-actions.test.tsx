import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { respond, problem, stubApi } from "@/test/api-mock";
import { signInAs } from "@/test/auth";
import { makeAdminOrder } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import { availableActions, OrderActions } from "./order-actions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/admin/orders/LK-ABCD2345" }));

const NUMBER = "LK-ABCD2345";
const route = (action: string) => `POST /api/v1/admin/orders/${NUMBER}/${action}`;

// Илгээх, хүргэх нь агуулахын ажилтных, цуцлах, буцаах нь админых.
beforeEach(() => signInAs("warehouse"));
afterEach(() => vi.unstubAllGlobals());

describe("availableActions", () => {
  it.each([
    ["pending", { ship: false, deliver: false, cancel: true, refund: false }],
    ["paid", { ship: true, deliver: false, cancel: false, refund: true }],
    ["shipped", { ship: false, deliver: true, cancel: false, refund: true }],
    ["delivered", { ship: false, deliver: false, cancel: false, refund: true }],
    ["cancelled", { ship: false, deliver: false, cancel: false, refund: false }],
    ["refunded", { ship: false, deliver: false, cancel: false, refund: false }],
  ] as const)("for a %s order", (status, expected) => {
    expect({
      ...availableActions(status, "warehouse"),
      ...Object.fromEntries(
        Object.entries(availableActions(status, "admin")).filter(([action]) => action === "cancel" || action === "refund"),
      ),
    }).toEqual(expected);
  });

  it("gives each action to one role only", () => {
    expect(availableActions("paid", "warehouse")).toEqual({ ship: true, deliver: false, cancel: false, refund: false });
    expect(availableActions("paid", "admin")).toEqual({ ship: false, deliver: false, cancel: false, refund: true });
    expect(availableActions("pending", "admin").cancel).toBe(true);
    expect(availableActions("pending", "warehouse").cancel).toBe(false);
    expect(availableActions("shipped", "warehouse").deliver).toBe(true);
    expect(availableActions("shipped", "admin").deliver).toBe(false);
    expect(availableActions("paid", "customer")).toEqual({ ship: false, deliver: false, cancel: false, refund: false });
    expect(availableActions("paid", undefined)).toEqual({ ship: false, deliver: false, cancel: false, refund: false });
  });
});

describe("OrderActions", () => {
  it("offers nothing for an order that is finished", () => {
    stubApi({});
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "refunded" })} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers a warehouse worker shipping, but no refund, for a paid order", () => {
    stubApi({});
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

    expect(screen.getByRole("button", { name: "Mark as shipped" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refund" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel order" })).not.toBeInTheDocument();
  });

  it("offers an administrator the refund, but no shipping, for a paid order", () => {
    signInAs("admin");
    stubApi({});
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

    expect(screen.getByRole("button", { name: "Refund" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as shipped" })).not.toBeInTheDocument();
  });

  describe("shipping", () => {
    it("asks for a carrier and a tracking number before calling the API", async () => {
      const api = stubApi({});
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Mark as shipped" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.click(within(dialog).getByRole("button", { name: "Mark as shipped" }));

      expect(await within(dialog).findByText("Enter the carrier")).toBeInTheDocument();
      expect(within(dialog).getByText("Enter the tracking number")).toBeInTheDocument();
      expect(api.calls).toHaveLength(0);
    });

    it("sends the shipment and closes", async () => {
      const api = stubApi({
        [route("ship")]: respond(makeAdminOrder({ status: "shipped" })),
        "GET /api/v1/admin/orders": respond({ items: [], total: 0, page: 1, page_size: 25, pages: 0, status_counts: {} }),
      });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Mark as shipped" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Carrier"), "DHL");
      await userEvent.type(within(dialog).getByLabelText("Tracking number"), "  JD0146 0000 1234 ");
      await userEvent.click(within(dialog).getByRole("button", { name: "Mark as shipped" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      const call = api.calls.find((c) => c.method === "POST");
      expect(call?.path).toBe(`/api/v1/admin/orders/${NUMBER}/ship`);
      expect(call?.body).toEqual({ carrier: "DHL", tracking_number: "JD0146 0000 1234" });
    });

    it("stays open when the order has moved on in the meantime", async () => {
      stubApi({
        [route("ship")]: problem(409, "Cannot ship this order", { detail: "A shipped order cannot be shipped." }),
      });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Mark as shipped" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Carrier"), "UPS");
      await userEvent.type(within(dialog).getByLabelText("Tracking number"), "1Z999");
      await userEvent.click(within(dialog).getByRole("button", { name: "Mark as shipped" }));

      await waitFor(() => expect(within(dialog).getByRole("button", { name: "Mark as shipped" })).toBeEnabled());
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });

  describe("delivering", () => {
    it("confirms, then marks the order delivered", async () => {
      const api = stubApi({ [route("deliver")]: respond(makeAdminOrder({ status: "delivered" })) });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "shipped" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Mark as delivered" }));
      const dialog = await screen.findByRole("dialog");
      expect(api.calls).toHaveLength(0);
      await userEvent.click(within(dialog).getByRole("button", { name: "Mark as delivered" }));

      await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/deliver"))).toBe(true));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });
  });

  describe("cancelling", () => {
    beforeEach(() => signInAs("admin"));

    it("cancels an unpaid order with a note", async () => {
      const api = stubApi({ [route("cancel")]: respond(makeAdminOrder({ status: "cancelled" })) });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "pending", payment: null })} />);

      await userEvent.click(screen.getByRole("button", { name: "Cancel order" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Note (optional)"), "  Customer called ");
      await userEvent.click(within(dialog).getByRole("button", { name: "Cancel order" }));

      await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/cancel"))).toBe(true));
      expect(api.calls.find((c) => c.path.endsWith("/cancel"))?.body).toEqual({ reason: "Customer called" });
    });

    it("needs no note", async () => {
      const api = stubApi({ [route("cancel")]: respond(makeAdminOrder({ status: "cancelled" })) });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "pending", payment: null })} />);

      await userEvent.click(screen.getByRole("button", { name: "Cancel order" }));
      await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel order" }));

      await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/cancel"))).toBe(true));
      expect(api.calls.find((c) => c.path.endsWith("/cancel"))?.body).toBeUndefined();
    });
  });

  describe("refunding", () => {
    beforeEach(() => signInAs("admin"));

    it("shows what will be refunded and needs a reason", async () => {
      const api = stubApi({});
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "delivered" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Refund" }));
      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent("$74.97");
      await userEvent.click(within(dialog).getByRole("button", { name: "Refund order" }));

      expect(await within(dialog).findByText("Say why it is being refunded")).toBeInTheDocument();
      expect(api.calls).toHaveLength(0);
    });

    it("puts goods that never left back in stock by default, and shipped ones not", async () => {
      stubApi({});
      const paid = renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);
      await userEvent.click(screen.getByRole("button", { name: "Refund" }));
      expect(await screen.findByRole("checkbox", { name: "Put the items back in stock" })).toBeChecked();
      paid.unmount();

      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "shipped" })} />);
      await userEvent.click(screen.getByRole("button", { name: "Refund" }));
      expect(await screen.findByRole("checkbox", { name: "Put the items back in stock" })).not.toBeChecked();
    });

    it("sends the reason and the stock decision", async () => {
      const api = stubApi({ [route("refund")]: respond(makeAdminOrder({ status: "refunded" })) });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "delivered" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Refund" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Reason"), "Arrived damaged");
      await userEvent.click(within(dialog).getByRole("checkbox", { name: "Put the items back in stock" }));
      await userEvent.click(within(dialog).getByRole("button", { name: "Refund order" }));

      await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/refund"))).toBe(true));
      expect(api.calls.find((c) => c.path.endsWith("/refund"))?.body).toEqual({ reason: "Arrived damaged", restock: true });
    });

    it("stays open when the payment provider is down", async () => {
      stubApi({ [route("refund")]: problem(502, "Payment provider error") });
      renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);

      await userEvent.click(screen.getByRole("button", { name: "Refund" }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Reason"), "Changed mind");
      await userEvent.click(within(dialog).getByRole("button", { name: "Refund order" }));

      await waitFor(() => expect(within(dialog).getByRole("button", { name: "Refund order" })).toBeEnabled());
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });
});

describe("OrderActions for a store pickup order", () => {
  it("marks it ready without asking for a carrier", async () => {
    const api = stubApi({ [route("ship")]: respond(makeAdminOrder({ status: "shipped", shipping_method: "pickup" })) });
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid", shipping_method: "pickup" })} />);
    expect(screen.queryByRole("button", { name: "Mark as shipped" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark ready for pickup" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.queryByRole("textbox")).not.toBeInTheDocument();
    await userEvent.click(dialog.getByRole("button", { name: "Mark ready for pickup" }));

    await waitFor(() => expect(api.count(route("ship"))).toBe(1));
    expect(api.calls.find((call) => call.method === "POST")?.body).toEqual({});
  });

  it("asks whether it was collected instead of delivered", async () => {
    stubApi({});
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "shipped", shipping_method: "pickup" })} />);

    await userEvent.click(screen.getByRole("button", { name: "Mark collected" }));

    expect(await screen.findByRole("heading", { name: "Has the customer collected it?" })).toBeInTheDocument();
  });

  // API нь цуцлах, буцаах шалтгааныг 200 тэмдэгт хүртэл авдаг (`schemas/admin/orders.py::Reason`):
  // илүү урт бичүүлбэл илгээх үед нь татгалзана.
  it("never lets a refund reason grow past what the API accepts", async () => {
    signInAs("admin");
    const api = stubApi({ [route("refund")]: respond(makeAdminOrder({ status: "refunded" })) });
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "paid" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Refund" }));
    const dialog = within(screen.getByRole("dialog"));

    await userEvent.click(dialog.getByLabelText("Reason"));
    await userEvent.paste("x".repeat(250));
    await userEvent.click(dialog.getByRole("button", { name: "Refund order" }));

    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect((api.calls[0]!.body as { reason: string }).reason).toHaveLength(200);
  });

  it("limits the note of a cancellation to the same length", async () => {
    signInAs("admin");
    stubApi({});
    renderWithQuery(<OrderActions order={makeAdminOrder({ status: "pending" })} />);

    await userEvent.click(screen.getByRole("button", { name: "Cancel order" }));

    expect(within(screen.getByRole("dialog")).getByLabelText("Note (optional)")).toHaveAttribute("maxlength", "200");
  });
});
