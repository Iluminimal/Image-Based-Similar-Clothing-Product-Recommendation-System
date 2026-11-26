import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { problem, respond, stubApi } from "@/test/api-mock";
import { signInAs } from "@/test/auth";
import { makeOrder, makeOrderRequest } from "@/test/fixtures";
import { renderWithQuery } from "@/test/render";
import { OrderRequests } from "./order-requests";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const NUMBER = "LK-ABCD2345";
const CREATE = `POST /api/v1/orders/${NUMBER}/requests`;

beforeEach(() => signInAs("customer"));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("OrderRequests", () => {
  it("shows nothing when there is nothing to ask for and nothing was asked", () => {
    const { container } = renderWithQuery(<OrderRequests order={makeOrder({ status: "shipped" })} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("offers only what the server says applies, with the last day for a return", () => {
    renderWithQuery(
      <OrderRequests
        order={makeOrder({ status: "delivered", available_request: "return", return_deadline: "2026-10-25T14:00:00Z" })}
      />,
    );

    expect(screen.getByRole("button", { name: "Request a return" })).toBeInTheDocument();
    expect(screen.getByText(/until October 25, 2026/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request cancellation" })).not.toBeInTheDocument();
  });

  it("asks for a reason, and for details when the reason is something else", async () => {
    const api = stubApi({ [CREATE]: respond(makeOrder()) });
    renderWithQuery(<OrderRequests order={makeOrder({ available_request: "cancel" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Request cancellation" }));
    const dialog = within(screen.getByRole("dialog", { name: "Cancel this order" }));

    await userEvent.click(dialog.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(dialog.getByRole("alert")).toHaveTextContent("Choose a reason"));
    expect(dialog.queryByRole("option", { name: "Doesn't fit" })).not.toBeInTheDocument();

    await userEvent.selectOptions(dialog.getByLabelText("Reason"), "other");
    await userEvent.click(dialog.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(dialog.getByRole("alert")).toHaveTextContent("Tell us what happened"));
    expect(api.calls).toHaveLength(0);

    await userEvent.type(dialog.getByLabelText("Tell us more"), "  Moving away  ");
    await userEvent.click(dialog.getByRole("button", { name: "Send request" }));

    await waitFor(() =>
      expect(api.calls.find((call) => call.method === "POST")?.body).toEqual({
        kind: "cancel",
        reason: "other",
        details: "Moving away",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Request sent. We'll email you our decision.");
  });

  it("says why when the order has moved on, and keeps the form", async () => {
    stubApi({ [CREATE]: () => problem(409, "Not allowed", { type: "urn:angel:problem:order-request-not-allowed" }) });
    renderWithQuery(<OrderRequests order={makeOrder({ available_request: "cancel" })} />);
    await userEvent.click(screen.getByRole("button", { name: "Request cancellation" }));
    await userEvent.selectOptions(screen.getByLabelText("Reason"), "changed_mind");

    await userEvent.click(screen.getByRole("button", { name: "Send request" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "That request is no longer possible for this order. Refresh the order to see where it stands.",
      ),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("lets a request be taken back only before it is decided", async () => {
    const api = stubApi({ [`${CREATE}/5/withdraw`]: respond(makeOrder()) });
    renderWithQuery(<OrderRequests order={makeOrder({ requests: [makeOrderRequest({ id: 5 })] })} />);
    expect(screen.getByText("Waiting for a decision")).toBeInTheDocument();
    expect(screen.getByText(/Changed my mind/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Withdraw request" }));

    await waitFor(() => expect(api.calls).toHaveLength(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Your request is withdrawn."));
  });

  it("tells an approved return where to take the goods", () => {
    renderWithQuery(
      <OrderRequests
        order={makeOrder({
          status: "delivered",
          return_address: "Peace Avenue 1",
          requests: [makeOrderRequest({ kind: "return", reason: "wrong_size", status: "approved" })],
        })}
      />,
    );

    expect(screen.getByText("Peace Avenue 1")).toBeInTheDocument();
    expect(screen.getByText("Include your order number: LK-ABCD2345")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw request" })).not.toBeInTheDocument();
  });

  it("shows why a request was declined", () => {
    renderWithQuery(
      <OrderRequests order={makeOrder({ requests: [makeOrderRequest({ status: "declined", decision_note: "Already packed" })] })} />,
    );

    expect(screen.getByText("We couldn't cancel this order.")).toBeInTheDocument();
    expect(screen.getByText("From the shop: Already packed")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
