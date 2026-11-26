/**
 * Утасны дэлгэц (390px): хуудас хэвтээ тийш гулсахгүй, чухал зүйл дэлгэцэндээ багтана. Монгол
 * бичвэр англиас урт тул хоёр хэлээр шалгана. Хөтчийн өргөнийг хэмжинэ; бодит утсыг орлохгүй.
 */
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { addAddress, addToCart, placePaidOrder, shipAndDeliver, warehouseSession } from "./support/api";

const PHONE = { width: 390, height: 844 };
const LANGUAGES = ["en", "mn"] as const;

/** Англи cookie-гүй бол сайт монголоор нээгдэнэ. */
async function speak(page: Page, language: (typeof LANGUAGES)[number]) {
  await page.context().clearCookies({ name: "NEXT_LOCALE" });
  if (language === "en") {
    const { hostname } = new URL(process.env.E2E_BASE_URL ?? "http://localhost:3000");
    await page.context().addCookies([{ name: "NEXT_LOCALE", value: "en", domain: hostname, path: "/" }]);
  }
}

async function open(page: Page, path: string) {
  await page.setViewportSize(PHONE);
  await page.goto(path, { waitUntil: "networkidle" });
  await expect(page.locator("h1").first()).toBeVisible();
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0); // skeleton биш, жинхэнэ агуулга
}

/** Хуудас дэлгэцээс хэдэн пиксел өргөн бэ. */
const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

async function expectToFit(page: Page, paths: string[]) {
  for (const language of LANGUAGES) {
    await speak(page, language);
    for (const path of paths) {
      await open(page, path);
      await expect(page.locator("html")).toHaveAttribute("lang", language);
      expect.soft(await overflow(page), `${path} (${language}) is wider than the phone, px`).toBeLessThanOrEqual(0);
    }
  }
}

test("the shop fits a phone for a visitor", async ({ page, products }) => {
  const product = products[0]!;
  await expectToFit(page, [
    "/", "/products", "/products?q=улаан цэцэгтэй цамц", "/c/women", `/products/${product.id}/${product.slug}`,
    "/search", "/cart", "/login", "/forgot-password",
  ]);
});

test("a customer's pages fit a phone, with a long address at checkout", async ({ shopperPage: page, account, api, products }) => {
  const worker = await warehouseSession(api);
  const number = await placePaidOrder(api, account, products[1]!.id);
  await shipAndDeliver(api, worker, number);
  await addToCart(api, account, products[0]!.id);
  await addAddress(api, account);

  await expectToFit(page, [
    "/account/orders", `/account/orders/${number}`, "/account/addresses", "/account/wishlist", "/account/profile",
    "/cart", "/checkout",
  ]);
});

test("the pay button at checkout is wholly on the screen", async ({ shopperPage: page, account, api, products }) => {
  await addToCart(api, account, products[0]!.id);
  await addAddress(api, account);
  for (const language of LANGUAGES) {
    await speak(page, language);
    await open(page, "/checkout");
    const pay = page.getByRole("button", { name: language === "en" ? /Pay now/ : /төлөх/i }).last();
    await expect(pay).toBeVisible();
    const box = (await pay.boundingBox())!;
    expect.soft(box.x, `pay button left edge (${language})`).toBeGreaterThanOrEqual(0);
    expect.soft(box.x + box.width, `pay button right edge (${language})`).toBeLessThanOrEqual(PHONE.width);
  }
});

test("the warehouse's pages fit a phone", async ({ warehousePage: page, account, api, products }) => {
  const number = await placePaidOrder(api, account, products[2]!.id);

  await expectToFit(page, ["/admin", "/admin/orders", `/admin/orders/${number}`, "/admin/products", "/admin/products/new"]);
});

test("the administrator's pages fit a phone", async ({ adminPage: page, account, api, products }) => {
  const number = await placePaidOrder(api, account, products[3]!.id);

  await expectToFit(page, [
    "/admin", "/admin/orders?status=requests", `/admin/orders/${number}`, "/admin/customers", "/admin/reviews",
    "/admin/activity",
  ]);
});

test("large amounts and long names stay inside the dashboard on a phone", async ({ adminPage: page, account, api, products }) => {
  await placePaidOrder(api, account, products[4]!.id); // "сүүлийн захиалга"-д мөр гарна
  const longName = "Бадамцэцэгийн Энхтүвшингийн Мөнхжаргалмаагийн нэрэмжит дэлгүүрийн захиалагч";
  // Хэдэн зуун сая төгрөгийн борлуулалт, урт нэр: туршилтын санд ийм өгөгдөл байдаггүй.
  await page.route("**/api/v1/admin/stats?*", async (route) => {
    const response = await route.fetch();
    const stats = await response.json();
    stats.revenue_cents = { current: 98_765_432_100, previous: 87_654_321_000 };
    stats.average_order_cents = { current: 12_345_678_900, previous: 100 };
    for (const order of stats.recent_orders) order.customer_name = longName;
    for (const product of [...stats.top_products, ...stats.low_stock]) product.name = longName;
    await route.fulfill({ response, json: stats });
  });
  await open(page, "/admin");
  await expect(page.getByText("₮987,654,321")).toBeVisible();

  const spilling = await page.locator("dl > div").evaluateAll((tiles) =>
    tiles.flatMap((tile) => {
      const edge = tile.getBoundingClientRect().right;
      const value = tile.querySelector("dd span");
      if (!value) return [];
      const range = document.createRange();
      range.selectNodeContents(value); // бичвэрийн өөрийн өргөн, хайрцгийнх биш
      const text = range.getBoundingClientRect().right;
      return text > edge - 8 ? [`${value.textContent} ends ${Math.round(text - edge)}px from its tile's edge`] : [];
    }),
  );
  expect.soft(spilling).toEqual([]);
  expect(await overflow(page)).toBeLessThanOrEqual(0);
});

test("the product status tabs show every choice on a phone, and the form's sections keep apart", async ({ warehousePage: page, newProduct }) => {
  const product = await newProduct({ name: `Tabs ${Date.now()}` });
  for (const language of LANGUAGES) {
    await speak(page, language);
    await open(page, "/admin/products");
    const tabs = page.getByRole("navigation", { name: language === "en" ? "Filter by status" : "Төлөвөөр шүүх" });
    await expect(tabs.getByRole("link")).toHaveCount(3);
    const hidden = await tabs.evaluate((nav) => nav.scrollWidth - nav.clientWidth);
    expect.soft(hidden, `status tabs cut off (${language}), px`).toBeLessThanOrEqual(0);
  }

  await open(page, `/admin/products/${product.id}`);
  const boxes = await page.locator("form fieldset section").evaluateAll((sections) =>
    sections.map((section) => section.getBoundingClientRect()).map(({ top, bottom }) => ({ top, bottom })),
  );
  const gaps = boxes.slice(1).map((box, index) => Math.round(box.top - boxes[index]!.bottom));
  expect(gaps.length).toBeGreaterThanOrEqual(2);
  expect(Math.min(...gaps), `gaps between the form's sections: ${gaps}`).toBeGreaterThanOrEqual(12);
});
