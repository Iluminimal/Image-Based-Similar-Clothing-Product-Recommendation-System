import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "@/features/auth/auth-store";
import { respond, stubApi } from "@/test/api-mock";
import { testIntl } from "@/test/intl";
import { renderWithQuery } from "@/test/render";
import { AdminGate, RoleGate } from "./admin-gate";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/products",
}));

const user = { id: 1, email: "a@b.co", full_name: "Ada" };
const signIn = (role: "customer" | "admin" | "warehouse") =>
  useAuth.setState({ status: "signedIn", accessToken: "t", user: { ...user, role, avatar_url: null, has_password: true, phone: null, email_verified: false, phone_verified: false, providers: [] as string[] } });

const twoFactor = (required: boolean, enabled: boolean) => ({
  "GET /api/v1/auth/2fa": respond({ required, enabled, recovery_codes_left: enabled ? 10 : 0 }),
});

afterEach(() => vi.unstubAllGlobals());

beforeEach(() => {
  stubApi(twoFactor(false, false));
  replace.mockClear();
  useAuth.setState({ status: "unknown", accessToken: null, user: null });
});

describe("AdminGate", () => {
  it("tells a customer in Mongolian that the area is not theirs", () => {
    testIntl.locale = "mn";
    signIn("customer");
    render(<AdminGate>secret</AdminGate>);

    expect(screen.getByText("Танд энэ хэсэгт хандах эрх алга")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Дэлгүүр рүү буцах" })).toHaveAttribute("href", "/");
  });

  it("shows the content to an administrator", () => {
    signIn("admin");
    renderWithQuery(<AdminGate>secret catalogue tools</AdminGate>);
    expect(screen.getByText("secret catalogue tools")).toBeInTheDocument();
  });

  it("shows the content to a warehouse worker", () => {
    signIn("warehouse");
    renderWithQuery(<AdminGate>secret catalogue tools</AdminGate>);
    expect(screen.getByText("secret catalogue tools")).toBeInTheDocument();
  });

  it("tells a customer they have no access and renders nothing else", () => {
    signIn("customer");
    render(<AdminGate>secret catalogue tools</AdminGate>);

    expect(screen.getByRole("alert")).toHaveTextContent("You don't have access to this area");
    expect(screen.queryByText("secret catalogue tools")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("waits while the session is still being restored", () => {
    render(<AdminGate>secret catalogue tools</AdminGate>);

    expect(screen.getByLabelText("Checking your access")).toBeInTheDocument();
    expect(screen.queryByText("secret catalogue tools")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("sends a visitor who is signed out to the login page and back afterwards", async () => {
    useAuth.setState({ status: "signedOut", accessToken: null, user: null });
    render(<AdminGate>secret catalogue tools</AdminGate>);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fadmin%2Fproducts"));
    expect(screen.queryByText("secret catalogue tools")).not.toBeInTheDocument();
  });
});

describe("AdminGate with required two-factor sign-in", () => {
  it("asks a member of staff who has not set it up to do so, instead of showing the back office", async () => {
    stubApi(twoFactor(true, false));
    signIn("warehouse");
    renderWithQuery(<AdminGate>secret catalogue tools</AdminGate>);

    expect(await screen.findByRole("heading", { name: "Set up two-factor sign-in" })).toBeInTheDocument();
    expect(screen.queryByText("secret catalogue tools")).not.toBeInTheDocument();
  });

  it("walks through the password, the QR code and the recovery codes, and keeps the codes on screen", async () => {
    let enabled = false;
    const api = stubApi({
      "GET /api/v1/auth/2fa": () => respond({ required: true, enabled, recovery_codes_left: 10 })(),
      "POST /api/v1/auth/2fa/setup": respond({ secret: "JBSWY3DP", otpauth_uri: "otpauth://totp/x", qr_image: "data:image/svg+xml,x" }),
      "POST /api/v1/auth/2fa/enable": () => {
        enabled = true;
        return respond({ codes: ["abcde-fghjk", "mnpqr-stuvw"] })();
      },
    });
    signIn("admin");
    renderWithQuery(<AdminGate>secret catalogue tools</AdminGate>);

    await userEvent.type(await screen.findByLabelText("Your password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Set up" }));
    expect(await screen.findByRole("img", { name: /QR code/ })).toBeInTheDocument();
    expect(screen.getByText("JBSWY3DP")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from the app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));

    expect(await screen.findByText("abcde-fghjk")).toBeInTheDocument();
    expect(screen.queryByText("secret catalogue tools")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I saved them" }));

    expect(await screen.findByText("secret catalogue tools")).toBeInTheDocument();
    expect(api.calls.find((call) => call.path.endsWith("/2fa/enable"))?.body).toEqual({ code: "123456" });
  });
});

describe("RoleGate", () => {
  it("opens a section to the role it is for", () => {
    signIn("warehouse");
    render(<RoleGate allow="warehouse">new product form</RoleGate>);
    expect(screen.getByText("new product form")).toBeInTheDocument();
  });

  it("keeps the other staff role out and points it back to its own workspace", () => {
    signIn("admin");
    render(<RoleGate allow="warehouse">new product form</RoleGate>);

    expect(screen.queryByText("new product form")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("This section is not part of your role.");
    expect(screen.getByRole("link", { name: "Back to your workspace" })).toHaveAttribute("href", "/admin");
  });

  it("sends a warehouse worker who opens an admin-only section back to the warehouse board", () => {
    signIn("warehouse");
    render(<RoleGate allow="admin">customers</RoleGate>);

    expect(screen.queryByText("customers")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to your workspace" })).toHaveAttribute("href", "/admin");
  });
});
