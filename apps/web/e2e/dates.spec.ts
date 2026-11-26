/**
 * Монгол сайтын огноо жинхэнэ хөтөч дээр. Chrome (Chromium) монгол огнооны өгөгдөлгүй тул `Intl`-д
 * найдвал англиар гарч, server-ийн зурсантай таарахгүй (hydration алдаа). jsdom үүнийг илрүүлэхгүй:
 * Node бүх хэлний өгөгдөлтэй.
 */
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { addAddress, placePaidOrder, postReview, shipAndDeliver, warehouseSession } from "./support/api";

const MONGOLIAN_DAY = /\d{4} оны \d{1,2}-р сарын \d{1,2}/;
const ENGLISH_MONTH = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b/;

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test("review and order dates stay Mongolian once the page is running in the browser", async ({
  browser,
  api,
  account,
  newProduct,
}) => {
  const product = await newProduct({ name: `Dates ${Date.now()}` });
  await addAddress(api, account);
  const order = await placePaidOrder(api, account, product.id);
  await shipAndDeliver(api, await warehouseSession(api), order);
  await postReview(api, account, product.id, { rating: 5, title: "Сайн даавуу" });

  // Хэлний cookie-гүй: сайт монголоор. Сэтгэгдэл server-ээс зурагдаж ирдэг.
  const visitor = await (await browser.newContext({ storageState: { cookies: [], origins: [] } })).newPage();
  const visitorErrors = watchErrors(visitor);
  await visitor.goto(`/products/${product.id}`);
  const review = visitor.getByRole("listitem").filter({ hasText: "Сайн даавуу" });
  await expect(review).toContainText(MONGOLIAN_DAY);
  await visitor.waitForLoadState("networkidle");
  await expect(review).not.toContainText(ENGLISH_MONTH);
  expect(visitorErrors).toEqual([]);

  // Бүртгэлийн cookie-д тестийн англи хэлний сонголт дагаж ирдэг: түүнийг хасна.
  const cookies = account.cookies.filter((cookie) => cookie.name !== "NEXT_LOCALE");
  const context = await browser.newContext({ storageState: { cookies, origins: [] } });
  const shopper = await context.newPage();
  const shopperErrors = watchErrors(shopper);
  await shopper.goto("/account/orders");
  const row = shopper.getByRole("listitem").filter({ hasText: order });
  await expect(row).toContainText(MONGOLIAN_DAY);
  await expect(row).not.toContainText(ENGLISH_MONTH);
  await shopper.goto(`/account/orders/${order}`);
  await expect(shopper.getByRole("main")).toContainText(MONGOLIAN_DAY);
  await expect(shopper.getByRole("main")).not.toContainText(ENGLISH_MONTH);
  expect(shopperErrors).toEqual([]);

  await visitor.context().close();
  await context.close();
});
