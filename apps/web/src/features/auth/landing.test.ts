import { describe, expect, it } from "vitest";
import { landingPath } from "./landing";

describe("landingPath", () => {
  it("sends an administrator with no particular destination to the admin area", () => {
    expect(landingPath("/", "admin")).toBe("/admin");
  });

  it("sends a warehouse worker with no particular destination to the warehouse board", () => {
    expect(landingPath("/", "warehouse")).toBe("/admin");
  });

  it("keeps the page a warehouse worker asked for", () => {
    expect(landingPath("/admin/orders", "warehouse")).toBe("/admin/orders");
    expect(landingPath("/account/profile", "warehouse")).toBe("/account/profile");
  });

  it("keeps the page an administrator asked for", () => {
    expect(landingPath("/products", "admin")).toBe("/products");
    expect(landingPath("/admin/orders", "admin")).toBe("/admin/orders");
  });

  it.each(["/account", "/account/orders", "/account/orders/LK-ABCD2345", "/account/wishlist", "/account?tab=1"])(
    "takes staff who asked for %s straight to their profile",
    (next) => {
      expect(landingPath(next, "admin")).toBe("/account/profile");
      expect(landingPath(next, "warehouse")).toBe("/account/profile");
      expect(landingPath(next, "customer")).toBe(next);
    },
  );

  it("does not mistake another address for the account area", () => {
    expect(landingPath("/accounting", "admin")).toBe("/accounting");
  });

  it("sends customers and unknown roles home", () => {
    expect(landingPath("/", "customer")).toBe("/");
    expect(landingPath("/", undefined)).toBe("/");
    expect(landingPath("/cart", "customer")).toBe("/cart");
  });
});
