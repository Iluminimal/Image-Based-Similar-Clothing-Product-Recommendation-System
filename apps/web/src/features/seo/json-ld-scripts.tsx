import { serializeJsonLd } from "@/features/catalog/json-ld";

/**
 * Node бүрд тусдаа `<script type="application/ld+json">`. Дээд түвшинд массив бичих нь хүчинтэй JSON-LD.
 * Гэхдээ олон хэрэглэгч (crawler, browser extension) уншсан script-ээс `["@context"]`-ийг шууд авдаг тул
 * массив дээр алдаа гаргадаг.
 *
 * Nonce тавихгүй: `application/ld+json` ажиллуулдаг код биш тул CSP хамаарахгүй. Харин browser nonce
 * attribute-ыг нуудаг тул hydration-д "server, client таарахгүй" алдаа гардаг.
 */
export function JsonLdScripts({ nodes }: { nodes: readonly object[] }) {
  return nodes.map((node, i) => (
    <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(node) }} />
  ));
}
