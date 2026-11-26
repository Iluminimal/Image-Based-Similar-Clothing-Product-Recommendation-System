import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { signInAs } from "@/test/auth";
import { useAuth } from "./auth-store";
import { ShopperOnly } from "./shopper-only";

describe("ShopperOnly", () => {
  it("shows its content to a visitor and a customer", () => {
    useAuth.setState({ status: "signedOut", accessToken: null, user: null });
    const visitor = render(<ShopperOnly>Bag</ShopperOnly>);
    expect(screen.getByText("Bag")).toBeInTheDocument();
    visitor.unmount();

    signInAs("customer");
    render(<ShopperOnly>Bag</ShopperOnly>);
    expect(screen.getByText("Bag")).toBeInTheDocument();
  });

  it.each(["admin", "warehouse"] as const)("hides it from %s staff", (role) => {
    signInAs(role);
    render(<ShopperOnly>Bag</ShopperOnly>);

    expect(screen.queryByText("Bag")).not.toBeInTheDocument();
  });
});
