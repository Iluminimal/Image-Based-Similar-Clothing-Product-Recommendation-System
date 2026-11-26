"use client";

import Link from "next/link";
import { Tabs } from "radix-ui";
import { ProductRail } from "@/features/catalog/product-rail";
import type { Product } from "@/features/catalog/product";

type Tab = { value: string; label: string; href: string; products: Product[] };

/** Radix Tabs: идэвхтэй tab-ын жагсаалт л DOM-д байна (бусдын зураг ачаалагдахгүй). Сумаар шилжинэ. */
export function TrendingTabs({ title, seeAll, tabs }: { title: string; seeAll: string; tabs: Tab[] }) {
  return (
    <section aria-label={title} className="container-page pt-6 pb-4 md:pt-10">
      <Tabs.Root defaultValue={tabs[0]!.value}>
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4 md:mb-8">
          <h2 className="home-h2">{title}</h2>
          <Tabs.List aria-label={title} className="home-tabs">
            {tabs.map((tab) => (
              <Tabs.Trigger key={tab.value} value={tab.value} className="home-tab">
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </div>
        {tabs.map((tab) => (
          <Tabs.Content key={tab.value} value={tab.value} className="outline-none">
            <ProductRail products={tab.products} label={tab.label} />
            <p className="mt-4 text-right">
              <Link href={tab.href} className="home-link">
                {seeAll} →
              </Link>
            </p>
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </section>
  );
}
