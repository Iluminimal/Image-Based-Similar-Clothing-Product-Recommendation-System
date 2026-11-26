import { randomUUID } from "node:crypto";
import { test, expect } from "./fixtures";
import { addAddress, addToCart, warehouseSession, type Account } from "./support/api";
import { API_URL } from "./support/env";

const auth = (account: Account) => ({ Authorization: `Bearer ${account.token}` });

test("a price that changes during checkout is shown and has to be accepted before paying", async ({
  shopperPage: page,
  account,
  api,
  newProduct,
}) => {
  const product = await newProduct({ stock: 5 });
  await addToCart(api, account, product.id);
  await addAddress(api, account);
  await page.goto("/checkout");
  const pay = page.getByRole("button", { name: /Pay now/ });
  await expect(pay).toBeEnabled();
  const shown = await pay.innerText();

  const worker = await warehouseSession(api);
  const changed = await api.patch(`${API_URL}/api/v1/admin/products/${product.id}`, {
    headers: auth(worker),
    data: { price_cents: 9_990_000 },
  });
  expect(changed.ok()).toBe(true);
  await pay.click();

  await expect(page.getByText("The total has changed. Check the new amount, then pay again.")).toBeVisible();
  await expect(pay).not.toHaveText(shown);
  await expect(page).toHaveURL(/\/checkout$/);

  await pay.click();
  await expect(page).toHaveURL(/\/checkout\/confirmation\/LK-/);
});

test("a pickup order is made ready without a carrier and collected, and the shelf count follows", async ({
  warehousePage: staff,
  shopperPage: page,
  account,
  api,
  newProduct,
}) => {
  const product = await newProduct({ stock: 5 });
  await addToCart(api, account, product.id);
  const addressId = await addAddress(api, account);
  const placed = await api.post(`${API_URL}/api/v1/checkout`, {
    headers: { ...auth(account), "Idempotency-Key": `e2e-${randomUUID()}` },
    data: { address_id: addressId, shipping_method: "pickup" },
  });
  expect(placed.ok()).toBe(true);
  const { number } = ((await placed.json()) as { order: { number: string } }).order;
  const paid = await api.post(`${API_URL}/api/v1/checkout/orders/${number}/simulate-payment`, { headers: auth(account) });
  expect(paid.ok()).toBe(true);

  // Төлсөн ч аваагүй нэг ширхэг агуулахад байсаар байна.
  await staff.goto(`/admin/products/${product.id}`);
  await expect(staff.getByLabel("On the shelf")).toHaveValue("5");
  await expect(staff.getByText("Available to sell: 4 · held for orders: 1")).toBeVisible();

  await staff.goto(`/admin/orders/${number}`);
  await staff.getByRole("button", { name: "Mark ready for pickup" }).click();
  const ready = staff.getByRole("dialog");
  await expect(ready.getByRole("textbox")).toHaveCount(0);
  await ready.getByRole("button", { name: "Mark ready for pickup" }).click();
  await expect(staff.getByRole("button", { name: "Mark collected" })).toBeVisible();

  await page.goto(`/account/orders/${number}`);
  const history = page.getByRole("list", { name: "Order history" });
  await expect(history).toContainText("Ready for pickup");
  await expect(history).not.toContainText("Shipped");

  await staff.getByRole("button", { name: "Mark collected" }).click();
  await staff.getByRole("dialog").getByRole("button", { name: "Mark collected" }).click();
  await expect(staff.getByRole("button", { name: "Mark collected" })).toHaveCount(0);
  await page.reload();
  await expect(history).toContainText("Collected at the store");

  await staff.goto(`/admin/products/${product.id}`);
  await expect(staff.getByLabel("On the shelf")).toHaveValue("4");
});
