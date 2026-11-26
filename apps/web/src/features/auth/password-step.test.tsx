import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { json, problem, stubApi } from "@/test/api-mock";
import { renderWithQuery } from "@/test/render";
import { PasswordStep } from "./password-step";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn() }) }));

afterEach(() => vi.unstubAllGlobals());

const session = {
  access_token: "t",
  token_type: "bearer",
  expires_in: 900,
  user: { id: 1, email: "a@b.co", full_name: "Ada", role: "admin", avatar_url: null, has_password: true, phone: null, email_verified: true, phone_verified: false, providers: [] },
};

describe("PasswordStep with two-factor sign-in", () => {
  it("asks for the code only after the API wants it, then sends both", async () => {
    const api = stubApi({
      "POST /api/v1/auth/login": (call) => {
        const body = call.body as { totp_code?: string };
        if (!body.totp_code) return problem(401, "Code needed", { type: "urn:angel:problem:totp-required" });
        if (body.totp_code !== "123456") return problem(401, "Wrong code", { type: "urn:angel:problem:totp-invalid" });
        return json(session);
      },
      "GET /api/v1/cart": { body: { lines: [] } },
    });
    const signedIn = vi.fn();
    renderWithQuery(<PasswordStep email="a@b.co" onSignedIn={signedIn} onUseCode={() => {}} codeBusy={false} codeProblem={null} />);
    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const code = await screen.findByLabelText("Verification code");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await userEvent.type(code, "000000");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code isn't right.");

    await userEvent.clear(code);
    await userEvent.type(code, "123456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(signedIn).toHaveBeenCalled());
    expect(api.calls.filter((call) => call.path.endsWith("/login")).at(-1)?.body).toEqual({
      email: "a@b.co",
      password: "correct horse battery",
      totp_code: "123456",
    });
  });
});
