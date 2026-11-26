import { test, expect } from "./fixtures";
import { productPhoto } from "./support/api";

const upload = (photo: Buffer) => ({ name: "photo.webp", mimeType: "image/webp", buffer: photo });

test("the first screen is a headline with two ways in", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Find it from a photo." })).toBeVisible();
  await expect(page.getByRole("link", { name: /Try it now/ })).toHaveAttribute("href", "#demo");
  await page.getByRole("link", { name: "Browse new", exact: true }).click();
  await expect(page).toHaveURL(/\/products\?sort=newest$/);
});

test("the page is light by default and dark once Dark is picked", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  await expect(page.locator(".home")).toHaveCSS("background-color", "rgb(251, 251, 254)");

  await page.evaluate(() => localStorage.setItem("theme", "dark"));
  await page.reload();
  await expect(page.locator(".home")).toHaveCSS("background-color", "rgb(8, 9, 13)");
});

test("below the demo: the trending tabs and the new arrivals", async ({ page }) => {
  await page.goto("/");

  const trending = page.getByRole("region", { name: "Trending now" });
  await expect(trending.getByRole("tab", { name: "Women", selected: true })).toBeVisible();
  await trending.getByRole("tab", { name: "Men", exact: true }).click();
  await expect(trending.getByRole("tab", { name: "Men", exact: true, selected: true })).toBeVisible();
  await expect(trending.getByRole("link").first()).toHaveAttribute("href", /^\/(products|c)/);
  await expect(page.getByRole("region", { name: "New arrivals" }).getByRole("link").first()).toHaveAttribute("href", /^\/(products|c)/);
});

test("the demo searches a sample photo on the page itself and shows real matches", async ({ page }) => {
  await page.goto("/");
  const demo = page.getByRole("region", { name: "Try photo search" });
  await expect(demo.getByText("Drop a photo here")).toBeVisible();

  await demo.getByRole("button", { name: "Sample 1" }).click();

  await expect(demo.getByText(/Found in \d+ ms/)).toBeVisible({ timeout: 60_000 });
  await expect(demo.getByRole("group", { name: "Detected items" }).getByRole("button").first()).toBeVisible();
  await expect(demo.locator("article").first()).toBeVisible();
  await expect(demo.getByText(/\d+% match/).first()).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
});

test("the demo searches a photo the visitor chooses, and hands it to the full search page", async ({ page, api, products }) => {
  const photo = await productPhoto(api, products[0]!);
  await page.goto("/");
  const demo = page.getByRole("region", { name: "Try photo search" });

  await demo.getByTestId("demo-file").setInputFiles(upload(photo));
  await expect(demo.getByText(/Found in \d+ ms/)).toBeVisible({ timeout: 60_000 });
  await demo.getByRole("button", { name: "See all results" }).click();

  await expect(page).toHaveURL(/\/search$/);
  await expect(page.getByRole("status").filter({ hasText: /similar item|garments? found/ })).toBeVisible();
});

test("recently viewed appears after looking at a product", async ({ page, products }) => {
  const product = products[0]!;
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Recently viewed" })).toHaveCount(0);

  await page.goto(`/products/${product.id}/${product.slug}`);
  await expect(page.getByRole("heading", { level: 1, name: product.name })).toBeVisible();
  // Гарчиг серверээс бэлэн ирдэг; "үзсэн" гэдгийг хуудас browser дээр ажиллаж эхэлсний дараа тэмдэглэнэ.
  await page.waitForFunction(() => window.localStorage.getItem("angel:recently-viewed") !== null);
  await page.goto("/");

  const shelf = page.getByRole("region", { name: "Recently viewed" });
  await expect(shelf.getByRole("link", { name: new RegExp(product.name) }).first()).toBeVisible();
});

test("the hero opens word by word without ever hiding its headline", async ({ page }) => {
  await page.goto("/");

  const heading = page.getByRole("heading", { level: 1, name: "Find it from a photo." });
  await expect(heading).toBeVisible();
  await expect(heading.locator(".word")).toHaveCount(5);
});

test("with reduced motion nothing moves", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto("/");

  const animation = (selector: string) => page.locator(selector).first().evaluate((el) => getComputedStyle(el).animationName);
  expect(await animation(".word")).toBe("none");
  expect(await animation(".home-mesh i")).toBe("none");
  expect(await animation(".hero-rise")).toBe("none");
  await context.close();
});

test("a product card tilts towards the pointer and lets go when it leaves", async ({ page }) => {
  await page.goto("/products");

  const card = page.locator("[data-tilt]").first();
  const box = (await card.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.2, { steps: 4 });
  await expect(card).toHaveAttribute("data-tilting", "");
  await page.mouse.move(2, 2, { steps: 4 });
  await expect(card).not.toHaveAttribute("data-tilting", "");
});
