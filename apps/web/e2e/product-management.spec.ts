/**
 * Агуулахын ажилтны өдөр тутмын барааны үйлдэл: нэг даралтаар зарахаа болих ба буцаах, жагсаалтаас
 * үнэ ба тоо засах, устгах. Бараагаа тест өөрөө үүсгэнэ.
 */
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { addAddress, addToCart, placePaidOrder, stockOf, warehouseSession } from "./support/api";
import { API_URL } from "./support/env";

const onStore = async (api: Parameters<typeof stockOf>[0], id: number) =>
  (await api.get(`${API_URL}/api/v1/products/${id}`)).status();

const list = (name: string, extra = "") => `/admin/products?q=${encodeURIComponent(name)}${extra}`;
const sellSwitch = (page: Page, name: string) => page.getByRole("switch", { name: `Sell ${name}` });
const tab = (page: Page, name: string) => page.getByRole("navigation", { name: "Filter by status" }).getByRole("link", { name });

async function menu(page: Page, product: string, item: string) {
  await page.getByRole("button", { name: `More actions for ${product}` }).click();
  await page.getByRole("menuitem", { name: item }).click();
}

test("one tap stops selling, the row stays for undo, and the tabs count along", async ({ warehousePage: page, api, newProduct }) => {
  const product = await newProduct({ name: `Switch ${Date.now()}` });
  await page.goto(list(product.name, "&status=active"));
  const sell = sellSwitch(page, product.name);
  await expect(sell).toBeChecked();
  await expect(tab(page, "On sale 1")).toBeVisible();

  await sell.click();

  await expect(page.getByText(`“${product.name}” is no longer on sale.`)).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(sell).not.toBeChecked(); // "On sale" таб дээр ч мөр хэвээр
  await expect(tab(page, "On sale 0")).toBeVisible();
  await expect(tab(page, "Not selling 1")).toBeVisible();
  await expect.poll(() => onStore(api, product.id)).toBe(404);

  await page.getByRole("button", { name: "Undo" }).click();

  await expect(sell).toBeChecked();
  await expect(tab(page, "On sale 1")).toBeVisible();
  await expect.poll(() => onStore(api, product.id)).toBe(200);

  // Гараар: унтраалга дээр Space дарна.
  await sell.focus();
  await page.keyboard.press("Space");
  await expect(sell).not.toBeChecked();
  await expect.poll(() => onStore(api, product.id)).toBe(404);

  // Таб солиход жагсаалт шинэчлэгдэнэ.
  await tab(page, "Not selling 1").click();
  await expect(sellSwitch(page, product.name)).not.toBeChecked();
  await tab(page, "On sale 0").click();
  await expect(page.getByText("No products found")).toBeVisible();
});

test("a refused change puts the switch back and says why", async ({ warehousePage: page, newProduct }) => {
  const product = await newProduct({ name: `Refused ${Date.now()}` });
  await page.goto(list(product.name));
  await page.route("**/api/v1/admin/products/*/deactivate", (route) => route.abort("failed"));

  await sellSwitch(page, product.name).click();

  await expect(page.getByText("We can't reach the server. Check your connection and try again.")).toBeVisible();
  await expect(sellSwitch(page, product.name)).toBeChecked();
});

test("the price and the shelf count are changed straight from the list", async ({ warehousePage: page, api, newProduct }) => {
  const product = await newProduct({ name: `Quick ${Date.now()}`, stock: 20 });
  const worker = await warehouseSession(api);
  await page.goto(list(product.name));

  await menu(page, product.name, "Price and stock");
  const dialog = page.getByRole("dialog", { name: "Price and stock" });
  await dialog.getByLabel("Price (₮)").fill("45000");
  await dialog.getByLabel("On the shelf").fill("4");
  await dialog.getByLabel("On the shelf").press("Enter");

  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row", { name: new RegExp(product.name) })).toContainText("₮45,000");
  await expect.poll(() => stockOf(api, worker, product.id)).toBe(4);
  const stored = await (await api.get(`${API_URL}/api/v1/products/${product.id}`)).json();
  expect(stored.price_cents).toBe(4_500_000);
});

test("a product nobody ordered is deleted; an ordered one is kept and can stop selling", async ({
  warehousePage: page,
  api,
  account,
  newProduct,
}) => {
  const tag = `Remove ${Date.now()}`;
  const unused = await newProduct({ name: `${tag} unused` });
  const bought = await newProduct({ name: `${tag} bought` });
  await addAddress(api, account);
  await placePaidOrder(api, account, bought.id);
  await addToCart(api, account, unused.id); // сагсанд байгаа нь устгахад саад болохгүй
  await page.goto(list(tag));

  await menu(page, unused.name, "Delete");
  const confirm = page.getByRole("dialog", { name: "Delete this product?" });
  await confirm.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText(`“${unused.name}” was deleted.`)).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(unused.name) })).toHaveCount(0);
  expect(await onStore(api, unused.id)).toBe(404);

  await menu(page, bought.name, "Delete");
  const refused = page.getByRole("dialog", { name: "This product can't be deleted" });
  await expect(refused.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await refused.getByRole("button", { name: "Stop selling" }).click();
  await expect(sellSwitch(page, bought.name)).not.toBeChecked();
  await expect.poll(() => onStore(api, bought.id)).toBe(404);
});

test("on the product page the status keeps unsaved typing, and delete returns to the same list", async ({
  warehousePage: page,
  api,
  newProduct,
}) => {
  const product = await newProduct({ name: `Page ${Date.now()}` });
  await page.goto(list(product.name));
  await page.getByRole("link", { name: `Edit ${product.name}` }).click();
  await expect(page.getByRole("heading", { level: 1, name: product.name })).toBeVisible();
  const colour = page.getByLabel("Colour (optional)");
  await colour.fill("Teal");
  await expect(page.getByText("Unsaved changes")).toBeVisible();

  await sellSwitch(page, product.name).click();

  await expect(page.getByText(/^Not shown in the shop/)).toBeVisible();
  await expect(colour).toHaveValue("Teal");

  await page.getByRole("button", { name: "Delete product" }).click();
  await page.getByRole("dialog", { name: "Delete this product?" }).getByRole("button", { name: "Delete" }).click();

  // Ижил шүүлтүүртэй жагсаалт руу буцна (зайг `+` эсвэл `%20` гэж бичсэн нь хамаагүй).
  await expect(page).toHaveURL((url) => url.pathname === "/admin/products" && url.searchParams.get("q") === product.name);
  await expect(page.getByText("No products found")).toBeVisible();
  expect(await onStore(api, product.id)).toBe(404);
});

test("the empty photo field reads in full, in English and Mongolian", async ({ warehousePage: page, newProduct }) => {
  const product = await newProduct({ name: `Photo ${Date.now()}` });
  // Файлын нэр (эсвэл "сонгоогүй") гарах бичиг: нарийн баганад тайрагдвал товчны нэр давтагдсан мэт уншигдана.
  const state = page.locator('input[type="file"]').first().locator("xpath=preceding-sibling::span[1]");
  const cutOff = async () => {
    await page.goto(`/admin/products/${product.id}`);
    await expect(state).toBeVisible();
    const pixels = await state.evaluate((element) => element.scrollWidth - element.clientWidth);
    expect(pixels, await state.innerText()).toBeLessThanOrEqual(0);
  };

  await cutOff();
  await page.context().clearCookies({ name: "NEXT_LOCALE" });
  await cutOff();
});
