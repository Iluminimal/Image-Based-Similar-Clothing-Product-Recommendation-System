import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { signInAs } from "@/test/auth";
import { AdminShell } from "./admin-shell";

vi.mock("./use-admin", () => ({ useNavBadges: () => ({ orders: 3 }) }));
vi.mock("./command-palette", () => ({ CommandPalette: () => null, useCommandPaletteHotkeys: () => {} }));
vi.mock("@/features/auth/account-menu", () => ({ AccountMenu: () => null }));
vi.mock("@/components/layout/theme-toggle", () => ({ ThemeToggle: () => null }));

describe.each(["admin", "warehouse"] as const)("AdminShell sidebar for the %s role", (role) => {
  beforeEach(() => {
    window.localStorage.clear();
    signInAs(role);
  });

  it("collapses to icons and opens again, keeping every link's name and badge", async () => {
    render(<AdminShell>content</AdminShell>);
    const orders = screen.getByRole("link", { name: /^Orders/ });
    expect(orders).not.toHaveAttribute("title");

    await userEvent.click(screen.getByRole("button", { name: "Collapse menu", expanded: true }));

    expect(orders).toHaveAttribute("title", "Orders");
    expect(orders).toHaveAccessibleName(/Orders.*3/);
    expect(screen.getByRole("complementary")).toHaveClass("md:w-[4.5rem]");

    await userEvent.click(screen.getByRole("button", { name: "Expand menu", expanded: false }));

    expect(orders).not.toHaveAttribute("title");
    expect(screen.getByRole("complementary")).toHaveClass("md:w-64");
  });

  it("keeps its button inside the sidebar, which takes the logo's place when collapsed", async () => {
    render(<AdminShell>content</AdminShell>);
    const sidebar = screen.getByRole("complementary");
    const toggle = screen.getByRole("button", { name: "Collapse menu" });
    expect(sidebar).toContainElement(toggle);
    expect(screen.getByTestId("admin-brand")).not.toHaveClass("md:hidden");

    await userEvent.click(toggle);

    // The same button, so keyboard focus stays on it.
    expect(screen.getByRole("button", { name: "Expand menu" })).toBe(toggle);
    expect(toggle).toHaveFocus();
    expect(screen.getByTestId("admin-brand")).toHaveClass("md:hidden");
  });

  it("remembers the choice on the next visit", async () => {
    const first = render(<AdminShell>content</AdminShell>);
    await userEvent.click(screen.getByRole("button", { name: "Collapse menu" }));
    first.unmount();

    render(<AdminShell>content</AdminShell>);

    expect(screen.getByRole("button", { name: "Expand menu" })).toBeInTheDocument();
  });
});
