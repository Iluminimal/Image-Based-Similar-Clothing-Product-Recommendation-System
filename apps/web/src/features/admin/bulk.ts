/**
 * `items` бүр дээр `fn`-ийг ажиллуулна, нэг зэрэг хамгийн ихдээ `limit` ширхэг (олон барааг нэг дор хасахад
 * API-г хэт ачаалахгүйн тулд). Нэг нь амжилтгүй болсон ч бусад үргэлжилнэ. Бүх үр дүнг анхны дарааллаар нь
 * буцаана.
 */
export async function runLimited<T, R>(
  items: readonly T[],
  limit: number,
  fn: (item: T) => Promise<R>,
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next++;
      try {
        results[index] = { status: "fulfilled", value: await fn(items[index]!) };
      } catch (reason) {
        results[index] = { status: "rejected", reason };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

/** `runLimited`-ийн үр дүнгээс амжилттай болон амжилтгүй болсны тоог гаргана. */
export function tally(results: readonly PromiseSettledResult<unknown>[]) {
  const done = results.filter((result) => result.status === "fulfilled").length;
  return { done, failed: results.length - done };
}
