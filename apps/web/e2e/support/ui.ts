import { expect, type Locator, type Page } from "@playwright/test";
import type { CatalogProduct } from "./api";

/** Header-ийн хайлтын panel-ийг (томруулагч) нээж, талбарыг нь буцаана. */
export async function openSearch(page: Page) {
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const box = page.getByRole("combobox");
  await expect(box).toBeVisible();
  await expect(box).toBeFocused();
  return box;
}

// Утасны tab bar-д мөн сагсны товч байдаг (компьютер дээр нуугдсан): харагдаж байгааг нь авна.
export const cartButton = (page: Page) => page.locator('button[aria-label^="Bag"]:visible');

export async function openProduct(page: Page, product: CatalogProduct) {
  await page.goto(`/products/${product.id}/${product.slug}`);
  await expect(page.getByRole("heading", { level: 1, name: product.name })).toBeVisible();
}

/** Барааны санал болгож буй эхний хэмжээг сонгоно (том хүн, хүүхэд, гутлын хэмжээ бүгд өөр). */
export async function chooseSize(page: Page): Promise<string> {
  const label = page.locator("fieldset label").first();
  const size = (await label.innerText()).trim();
  await label.click();
  return size;
}

/** Хэмжээ сонгож бараа нэмнэ; Bag panel нээлттэй үлдэнэ. Сонгосон хэмжээг буцаана. */
export async function addToCartFromProductPage(page: Page, product: CatalogProduct): Promise<string> {
  await openProduct(page, product);
  const size = await chooseSize(page);
  await page.getByRole("button", { name: /add to bag/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  return size;
}

export async function signInThroughTheForm(page: Page, email: string, password: string) {
  await page.getByLabel("Email or phone number").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

/** Дэлгүүрийн үнэ англи дэлгэцэд: `₮175,800` (хадгалдаг нь мөнгө, 100 = 1 төгрөг). */
export const money = (cents: number) => `₮${Math.round(cents / 100).toLocaleString("en-US")}`;

/**
 * Тестүүд каталогийн өөр өөр бараа сонгоно: зэрэг ажиллаж байгаа худалдан авалтууд нэг барааны сүүлчийн
 * ширхэг дээр мөргөлдөх нь ховор болно.
 */
export function pickProduct(products: CatalogProduct[], testIndex: number): CatalogProduct {
  return products[testIndex % products.length]!;
}

/** Нууц үггүй бүртгэлийн dialog: баталгаажуулах код авч оруулна (OTP_DEV_CODE). */
export async function confirmItIsYou(dialog: Locator, code: string) {
  await dialog.getByRole("button", { name: "Send confirmation code" }).click();
  await expect(dialog.getByText(/^Code sent to/)).toBeVisible();
  await dialog.getByLabel("Confirmation code").fill(code);
}
