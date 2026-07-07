"use client";

import {
  emptyParlayCategoryCatalog,
  type ParlayCategoryMeta,
} from "@/lib/parlay-categories";
import { FilterTabs } from "@/components/ui/FilterTabs";

interface ParlayCategoryTabsProps {
  categories?: ParlayCategoryMeta[];
  activeSlug?: string | null;
  onSelect?: (slug: string | null) => void;
}

export function ParlayCategoryTabs({
  categories,
  activeSlug,
  onSelect,
}: ParlayCategoryTabsProps) {
  const tabs = categories?.length ? categories : emptyParlayCategoryCatalog();

  return (
    <FilterTabs
      label="Browse by time window"
      hint="24–48h = games starting soon. Multi-day = legs spread across several days."
      allLabel="All parlays"
      accent="orange"
      activeId={activeSlug ?? null}
      onSelect={onSelect ?? (() => {})}
      items={tabs.map((cat) => ({
        id: cat.slug,
        label: cat.short_label,
        count: cat.count,
        description: cat.description,
      }))}
      guideLinks={tabs.map((cat) => ({
        href: `/parlays/category/${cat.slug}`,
        label: `${cat.title} guide →`,
      }))}
    />
  );
}
