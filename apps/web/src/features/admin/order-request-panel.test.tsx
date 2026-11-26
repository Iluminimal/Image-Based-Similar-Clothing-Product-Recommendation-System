import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { respond, stubApi } from "@/test/api-mock";
import { signInAs } from "@/test/auth";
import { makeAdminOrder, makeAdminOrderRequest } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import { availableActions, OrderActions } from "./order-actions";
import { OrderRequestPanel, requestActions } from "./order-request-panel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/admin/orders/LK-ABCD2345" }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const NUMBER = "LK-ABCD2345";
const route = (action: string) => `POST /api/v1/admin/orders/${NUMBER}/requests/9/${action}`;
const cancellation = makeAdminOrderRequest({ id: 9 });
const returning = (status: "requested" | "approved" | "received") =>
  makeAdminOrderRequest({ id: 9, kind: "return", reason: "wrong_size", status, restocked: status === "received" ? true : null });

afterEach(() => vi.unstubAllGlobals());

describe("requestActions", () => {
  it("gives the decision to an administrator and the goods to the warehouse", () => {
    expect(requestActions(returning("requested"), "admin")).toEqual({ approve: true, decline: true, receive: false });
    expect(requestActions(returning("requested"), "warehouse")).toEqual({ approve: false, decline: false, receive: false });
    expect(requestActions(returning("approved"), "admin")).toEqual({ approve: false, decline: true, receive: false });
    expect(requestActions(returning("approved"), "warehouse")).toEqual({ approve: false, decline: false, receive: true });
    expect(requestActions(returning("received"), "admin")).toEqual({ approve: false, decline: false, receive: false });
    expect(requestActions(undefined, "admin")).toEqual({ approve: false, decline: false, receive: false });
  });
});

describe("OrderRequestPanel", () => {
  it("is not there for an order nobody asked about", () => {
    signInAs("admin");
    const { container } = renderWithQuery(<OrderRequestPanel order={makeAdminOrder()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("approves a cancellation after saying that it refunds at once", async () => {
    signInAs("admin");
    const api = stubApi({ [route("approve")]: respond(makeAdminOrder()) });
    renderWithQuery(<OrderRequestPanel order={makeAdminOrder({ requests: [cancellation] })} />);

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = within(screen.getByRole("dialog", { name: "Approve the cancellation?" }));
    expect(dialog.getByText(/refunded in full now/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(api.calls.map((call) => call.method)).toContain("POST"));
    expect(api.calls[0]!.body).toBeUndefined();
  });

  it("does not decline without telling the customer why", async () => {
    signInAs("admin");
    const api = stubApi({ [route("decline")]: respond(makeAdminOrder()) });
    renderWithQuery(<OrderRequestPanel order={makeAdminOrder({ requests: [cancellation] })} />);
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    const dialog = within(screen.getByRole("dialog"));

    await userEvent.click(dialog.getByRole("button", { name: "Decline" }));
    expect(await dialog.findByText("Say why, so the customer knows")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);

    await userEvent.type(dialog.getByLabelText("Message to the customer"), "Already packed");
    await userEvent.click(dialog.getByRole("button", { name: "Decline" }));

    await waitFor(() => expect(api.calls[0]?.body).toEqual({ note: "Already packed" }));
  });

  it("tells the warehouse an order with a cancellation is on hold, and offers no shipping", () => {
    signInAs("warehouse");
    const order = makeAdminOrder({ status: "paid", requests: [cancellation] });
    renderWithQuery(
      <>
        <OrderActions order={order} />
        <OrderRequestPanel order={order} />
      </>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("this order can't ship until an administrator decides");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(availableActions("paid", "warehouse", true).ship).toBe(false);
  });

  it("lets the warehouse receive returned goods and keep damaged ones out of stock", async () => {
    signInAs("warehouse");
    const api = stubApi({ [route("receive")]: respond(makeAdminOrder()) });
    renderWithQuery(<OrderRequestPanel order={makeAdminOrder({ status: "delivered", requests: [returning("approved")] })} />);
    await userEvent.click(screen.getByRole("button", { name: "Mark goods received" }));
    const dialog = within(screen.getByRole("dialog"));

    await userEvent.click(dialog.getByRole("checkbox", { name: "Put the items back in stock" }));
    await userEvent.click(dialog.getByRole("button", { name: "Goods received" }));

    await waitFor(() => expect(api.calls[0]?.body).toEqual({ restock: false }));
  });

  it("does not offer to restock goods returned as faulty unless the warehouse says so", async () => {
    signInAs("warehouse");
    stubApi({});
    const faulty = makeAdminOrderRequest({ id: 9, kind: "return", reason: "defective", status: "approved" });
    renderWithQuery(<OrderRequestPanel order={makeAdminOrder({ status: "delivered", requests: [faulty] })} />);

    await userEvent.click(screen.getByRole("button", { name: "Mark goods received" }));

    expect(screen.getByRole("checkbox", { name: "Put the items back in stock" })).not.toBeChecked();
  });

  it("refunds a received return without asking about the stock again", async () => {
    signInAs("admin");
    const api = stubApi({ [`POST /api/v1/admin/orders/${NUMBER}/refund`]: respond(makeAdminOrder()) });
    // Төлсөн захиалгад "үлдэгдэлд буцаах" өгөгдмөлөөр сонгогддог ч хүлээн авсан бараанд биш.
    const order = makeAdminOrder({ status: "delivered", requests: [returning("received")] });
    renderWithQuery(<OrderActions order={order} />);
    await userEvent.click(screen.getByRole("button", { name: "Refund" }));
    const dialog = within(screen.getByRole("dialog"));

    expect(dialog.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(dialog.getByText(/The warehouse decided about the stock/)).toBeInTheDocument();
    await userEvent.type(dialog.getByLabelText("Reason"), "Returned");
    await userEvent.click(dialog.getByRole("button", { name: "Refund order" }));

    await waitFor(() => expect(api.calls[0]?.body).toEqual({ reason: "Returned", restock: false }));
  });
});
