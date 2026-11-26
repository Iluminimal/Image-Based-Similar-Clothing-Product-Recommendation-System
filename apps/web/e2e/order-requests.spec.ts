import { test, expect } from "./fixtures";
import { adminSession, orderOf, placePaidOrder, shipAndDeliver, stockOf, warehouseSession } from "./support/api";
import { API_URL } from "./support/env";
import { withEnglish } from "./support/locale";

test("a shopper asks to cancel, the warehouse holds the order and an administrator approves", async ({
  shopperPage: shopper,
  warehousePage: warehouse,
  adminPage: admin,
  account,
  api,
  newProduct,
}) => {
  const product = await newProduct({ stock: 5 });
  const number = await placePaidOrder(api, account, product.id);
  const staff = await adminSession(api);
  expect(await stockOf(api, staff, product.id)).toBe(4);

  await shopper.goto(`/account/orders/${number}`);
  await shopper.getByRole("button", { name: "Request cancellation" }).click();
  const form = shopper.getByRole("dialog", { name: "Cancel this order" });
  await form.getByRole("button", { name: "Send request" }).click();
  await expect(form.getByRole("alert")).toHaveText("Choose a reason");
  await form.getByLabel("Reason").selectOption("too_slow");
  await form.getByRole("button", { name: "Send request" }).click();
  const mine = shopper.getByRole("region", { name: "Cancellations and returns" });
  await expect(mine).toContainText("Waiting for a decision");
  await expect(shopper.getByRole("button", { name: "Request cancellation" })).toHaveCount(0);

  await warehouse.goto(`/admin/orders/${number}`);
  await expect(warehouse.getByRole("region", { name: "Customer request" })).toContainText("On hold");
  await expect(warehouse.getByRole("button", { name: "Mark as shipped" })).toHaveCount(0);

  await admin.goto("/admin/orders?status=requests");
  await admin.getByRole("link", { name: number }).first().click();
  const request = admin.getByRole("region", { name: "Customer request" });
  await expect(request).toContainText("It's taking too long");
  await request.getByRole("button", { name: "Approve" }).click();
  await admin.getByRole("dialog", { name: "Approve the cancellation?" }).getByRole("button", { name: "Approve" }).click();
  await expect(request).toContainText("Done");
  await expect(admin.getByRole("button", { name: "Refund" })).toHaveCount(0);

  expect((await orderOf(api, account, number)).status).toBe("refunded");
  expect(await stockOf(api, staff, product.id)).toBe(5);
  await shopper.reload();
  await expect(mine).toContainText("Your order is cancelled and refunded.");
});

test("a delivered order is returned: approved, received at the warehouse, then refunded", async ({
  shopperPage: shopper,
  warehousePage: warehouse,
  adminPage: admin,
  account,
  api,
  newProduct,
}) => {
  const product = await newProduct({ stock: 5 });
  const number = await placePaidOrder(api, account, product.id);
  await shipAndDeliver(api, await warehouseSession(api), number);
  const staff = await adminSession(api);

  await shopper.goto(`/account/orders/${number}`);
  await expect(shopper.getByText(/You can ask to return this order until/)).toBeVisible();
  await shopper.getByRole("button", { name: "Request a return" }).click();
  const form = shopper.getByRole("dialog", { name: "Return this order" });
  await form.getByLabel("Reason").selectOption("wrong_size");
  await form.getByRole("button", { name: "Send request" }).click();
  const mine = shopper.getByRole("region", { name: "Cancellations and returns" });
  await expect(mine).toContainText("Waiting for a decision");

  await admin.goto(`/admin/orders/${number}`);
  const asked = admin.getByRole("region", { name: "Customer request" });
  await asked.getByRole("button", { name: "Approve" }).click();
  const approve = admin.getByRole("dialog", { name: "Approve the return?" });
  await approve.getByLabel("Message to the customer (optional)").fill("Keep the tags on");
  await approve.getByRole("button", { name: "Approve" }).click();
  await expect(asked).toContainText("Waiting for the goods");

  await shopper.reload();
  await expect(mine).toContainText("Bring or send the items to:");
  await expect(mine).toContainText(`Include your order number: ${number}`);
  await expect(mine).toContainText("From the shop: Keep the tags on");

  await warehouse.goto("/admin");
  await warehouse.getByRole("region", { name: "Returns on the way" }).getByRole("link", { name: new RegExp(number) }).first().click();
  await warehouse.getByRole("button", { name: "Mark goods received" }).click();
  await warehouse.getByRole("dialog", { name: "Have the goods arrived?" }).getByRole("button", { name: "Goods received" }).click();
  await expect(warehouse.getByRole("region", { name: "Customer request" })).toContainText("Refund due");
  expect(await stockOf(api, staff, product.id)).toBe(5);

  await admin.reload();
  await expect(asked).toContainText("Use Refund to finish");
  await admin.getByRole("button", { name: "Refund" }).click();
  const refund = admin.getByRole("dialog", { name: "Refund this order?" });
  await expect(refund.getByRole("checkbox")).toHaveCount(0);
  await refund.getByLabel("Reason").fill("Return received");
  await refund.getByRole("button", { name: "Refund order" }).click();
  await expect(admin.getByRole("button", { name: "Refund" })).toHaveCount(0);

  // Нөөцөд нэг л удаа буцсан.
  expect(await stockOf(api, staff, product.id)).toBe(5);
  await shopper.reload();
  await expect(mine).toContainText("Your return is done and refunded.");
});

/**
 * Session-ий алдаа: хуудас шилжих эсвэл сүлжээ тасрахад сервер refresh token-ийг сольсон ч browser
 * шинэ cookie-г авдаггүй. Дараагийн хуудас хуучнаар сэргээхэд хэрэглэгч гарч болохгүй.
 */
test("a shopper stays signed in when the answer to a refresh never reached the browser", async ({
  shopperPage: page,
  account,
  playwright,
}) => {
  // Browser-ийн cookie-оор өөр газраас refresh: сервер сольсон, browser-т хуучин нь үлдсэн.
  const elsewhere = await playwright.request.newContext({ storageState: withEnglish(account.cookies) });
  const lost = await elsewhere.post(`${API_URL}/api/v1/auth/refresh`);
  expect(lost.status()).toBe(200);
  await elsewhere.dispose();

  await page.goto("/account/profile");

  await expect(page.getByRole("heading", { level: 2, name: "Profile" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name: "Profile" })).toBeVisible();
});

test("opening a product by an address without its slug keeps the shopper signed in", async ({
  shopperPage: page,
  newProduct,
}) => {
  const product = await newProduct();

  await page.goto(`/products/${product.id}`);

  await expect(page).toHaveURL(new RegExp(`/products/${product.id}/.+`));
  await expect(page.getByText("Only customers who have bought this product can review it.")).toBeVisible();
  await expect(page.getByText(/to review this product if you have bought it/)).toHaveCount(0);
});
