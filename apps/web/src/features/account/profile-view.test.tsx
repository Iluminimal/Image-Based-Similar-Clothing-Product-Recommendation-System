import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth, type SessionUser } from "@/features/auth/auth-store";
import { json, problem, respond, stubApi } from "@/test/api-mock";
import { renderWithQuery } from "@/test/render";
import { ProfileView } from "./profile-view";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }), usePathname: () => "/account/profile" }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const withPassword: SessionUser = {
  id: 1,
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  role: "customer",
  avatar_url: null,
  has_password: true, phone: null, email_verified: false, phone_verified: false,
  providers: [],
};
const googleOnly: SessionUser = { ...withPassword, has_password: false, phone: null, email_verified: false, phone_verified: false, providers: ["google"] };

const SESSIONS = "/api/v1/auth/sessions";
const SECURITY_EVENTS = "/api/v1/auth/security-events";

/**
 * `stubApi` дээр хуудасны үргэлж асуудаг хоосон төхөөрөмжийн жагсаалтыг нэмсэн; `calls` тэр
 * хүсэлтийг оруулдаггүй.
 */
function stubProfileApi(routes: Parameters<typeof stubApi>[0]) {
  const api = stubApi({ [`GET ${SESSIONS}`]: respond([]), [`GET ${SECURITY_EVENTS}`]: respond([]), ...routes });
  return {
    ...api,
    get calls() {
      return api.calls.filter((call) => call.path !== SESSIONS && call.path !== SECURITY_EVENTS);
    },
  };
}

function signIn(user: SessionUser) {
  useAuth.setState({ status: "signedIn", accessToken: "t", user });
}

beforeEach(() => push.mockReset());
afterEach(() => vi.unstubAllGlobals());

describe("ProfileView", () => {
  it.each(["admin", "warehouse"] as const)("does not offer %s staff a way to delete their account", (role) => {
    stubProfileApi({ "GET /api/v1/auth/2fa": { body: { enabled: false, required: false, recovery_codes_left: 0 } } });
    signIn({ ...withPassword, role });

    renderWithQuery(<ProfileView />);

    expect(screen.getByRole("button", { name: /Change password/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete my account/ })).not.toBeInTheDocument();
  });

  it("shows who you are and how you sign in", () => {
    signIn(googleOnly);
    renderWithQuery(<ProfileView />);

    expect(screen.getByDisplayValue("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(/Not set\. You sign in with Google/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Set a password/ })).toBeInTheDocument();
    expect(screen.getByText(/Not added\. Add one to sign in with a text-message code/)).toBeInTheDocument();
  });

  it("offers to change, not set, a password that exists", () => {
    signIn(withPassword);
    renderWithQuery(<ProfileView />);

    expect(screen.getByRole("button", { name: /Change password/ })).toBeInTheDocument();
    expect(screen.getByText(/Not connected/)).toBeInTheDocument();
  });

  it("saves a new name only once it has changed, and the header sees it", async () => {
    signIn(withPassword);
    const api = stubProfileApi({
      "PATCH /api/v1/auth/me": (call) => json({ ...withPassword, ...(call.body as object) }),
    });
    renderWithQuery(<ProfileView />);
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();

    const name = screen.getByLabelText("Full name");
    await userEvent.clear(name);
    await userEvent.type(name, "Ada King");
    await userEvent.click(save);

    await waitFor(() => expect(useAuth.getState().user?.full_name).toBe("Ada King"));
    expect(api.calls[0]?.body).toEqual({ full_name: "Ada King" });
    expect(save).toBeDisabled();
  });

  it("refuses an empty name without asking the API", async () => {
    signIn(withPassword);
    const api = stubProfileApi({});
    renderWithQuery(<ProfileView />);

    await userEvent.clear(screen.getByLabelText("Full name"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Enter your name")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  describe("password", () => {
    const session = { access_token: "fresh", token_type: "bearer", expires_in: 900 };

    it("lets a Google-only account set one with a fresh confirmation code instead", async () => {
      signIn(googleOnly);
      const api = stubProfileApi({
        "POST /api/v1/auth/reauth/request": { status: 202 },
        "PUT /api/v1/auth/password": { body: { ...session, user: { ...googleOnly, has_password: true, phone: null, email_verified: false, phone_verified: false } } },
      });
      renderWithQuery(<ProfileView />);

      await userEvent.click(screen.getByRole("button", { name: /Set a password/ }));
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).queryByLabelText("Current password")).not.toBeInTheDocument();
      await userEvent.type(within(dialog).getByLabelText("New password"), "a brand new passphrase");
      expect(within(dialog).getByText("Excellent")).toBeInTheDocument();
      await userEvent.type(within(dialog).getByLabelText("Confirm new password"), "a brand new passphrase");
      await userEvent.click(within(dialog).getByRole("button", { name: "Send confirmation code" }));
      await userEvent.type(within(dialog).getByLabelText("Confirmation code"), "123456");
      await userEvent.click(within(dialog).getByRole("button", { name: "Set password" }));

      await waitFor(() => expect(useAuth.getState().accessToken).toBe("fresh"));
      expect(api.calls.at(-1)?.body).toEqual({ new_password: "a brand new passphrase", reauth_code: "123456" });
      expect(useAuth.getState().user?.has_password).toBe(true);
    });

    it("asks for the current password, and says so when it is wrong", async () => {
      signIn(withPassword);
      stubProfileApi({ "PUT /api/v1/auth/password": problem(403, "Incorrect password", { type: "urn:angel:problem:invalid-credentials" }) });
      renderWithQuery(<ProfileView />);

      await userEvent.click(screen.getByRole("button", { name: /Change password/ }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("Current password"), "not it at all");
      await userEvent.type(within(dialog).getByLabelText("New password"), "a brand new passphrase");
      await userEvent.type(within(dialog).getByLabelText("Confirm new password"), "a brand new passphrase");
      await userEvent.click(within(dialog).getByRole("button", { name: "Change password" }));

      expect(await within(dialog).findByText("That isn't your current password")).toBeInTheDocument();
      expect(useAuth.getState().accessToken).toBe("t");
    });

    it("catches a short password and a mismatch before asking the API", async () => {
      signIn(googleOnly);
      const api = stubProfileApi({});
      renderWithQuery(<ProfileView />);

      await userEvent.click(screen.getByRole("button", { name: /Set a password/ }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.type(within(dialog).getByLabelText("New password"), "short");
      await userEvent.click(within(dialog).getByRole("button", { name: "Set password" }));
      expect(await within(dialog).findByText("Use at least 10 characters")).toBeInTheDocument();

      await userEvent.clear(within(dialog).getByLabelText("New password"));
      await userEvent.type(within(dialog).getByLabelText("New password"), "a brand new passphrase");
      await userEvent.type(within(dialog).getByLabelText("Confirm new password"), "something different");
      await userEvent.click(within(dialog).getByRole("button", { name: "Set password" }));
      expect(await within(dialog).findByText("The two passwords don't match")).toBeInTheDocument();
      expect(api.calls).toHaveLength(0);
    });
  });

  describe("deleting", () => {
    async function openDialog() {
      await userEvent.click(screen.getByRole("button", { name: /Delete my account/ }));
      return screen.findByRole("dialog");
    }

    it("stays disabled until the email is typed back (and the password given)", async () => {
      signIn(withPassword);
      renderWithQuery(<ProfileView />);
      const dialog = await openDialog();
      const confirm = within(dialog).getByRole("button", { name: "Delete account" });
      expect(confirm).toBeDisabled();

      await userEvent.type(within(dialog).getByLabelText("Your email"), "ADA@example.com");
      expect(confirm).toBeDisabled();
      await userEvent.type(within(dialog).getByLabelText("Your password"), "correct horse battery");

      expect(confirm).toBeEnabled();
    });

    it("deletes, signs out here and goes home", async () => {
      signIn(googleOnly);
      const api = stubProfileApi({
        "POST /api/v1/auth/reauth/request": { status: 202 },
        "DELETE /api/v1/auth/me": { status: 204 },
        "GET /api/v1/cart": { body: { lines: [] } },
      });
      renderWithQuery(<ProfileView />);
      const dialog = await openDialog();
      expect(within(dialog).queryByLabelText("Your password")).not.toBeInTheDocument();

      await userEvent.type(within(dialog).getByLabelText("Your email"), "ada@example.com");
      expect(within(dialog).getByRole("button", { name: "Delete account" })).toBeDisabled();
      await userEvent.click(within(dialog).getByRole("button", { name: "Send confirmation code" }));
      await userEvent.type(within(dialog).getByLabelText("Confirmation code"), "123456");
      await userEvent.click(within(dialog).getByRole("button", { name: "Delete account" }));

      await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
      const deletion = api.calls.find((call) => call.method === "DELETE");
      expect(deletion?.body).toEqual({ confirm: "ada@example.com", reauth_code: "123456" });
      expect(useAuth.getState().status).toBe("signedOut");
    });

    it("explains that unfinished orders have to be finished first", async () => {
      signIn(withPassword);
      stubProfileApi({
        "DELETE /api/v1/auth/me": problem(409, "Unfinished orders", { type: "urn:angel:problem:open-orders", count: 2 }),
      });
      renderWithQuery(<ProfileView />);
      const dialog = await openDialog();
      await userEvent.type(within(dialog).getByLabelText("Your email"), "ada@example.com");
      await userEvent.type(within(dialog).getByLabelText("Your password"), "correct horse battery");

      await userEvent.click(within(dialog).getByRole("button", { name: "Delete account" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("You have 2 unfinished orders (not delivered yet, or with a cancellation or return in progress)");
      expect(useAuth.getState().status).toBe("signedIn");
    });

    it("says when the password is wrong and stays signed in", async () => {
      signIn(withPassword);
      stubProfileApi({ "DELETE /api/v1/auth/me": problem(403, "Incorrect password", { type: "urn:angel:problem:invalid-credentials" }) });
      renderWithQuery(<ProfileView />);
      const dialog = await openDialog();

      await userEvent.type(within(dialog).getByLabelText("Your email"), "ada@example.com");
      await userEvent.type(within(dialog).getByLabelText("Your password"), "nope nope nope");
      await userEvent.click(within(dialog).getByRole("button", { name: "Delete account" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("That password isn't right.");
      expect(push).not.toHaveBeenCalled();
      expect(useAuth.getState().status).toBe("signedIn");
    });
  });
});
