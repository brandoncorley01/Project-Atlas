"use client";

import type { SportsCategoryMeta } from "@/lib/sports-categories";
import { FilterTabs } from "@/components/ui/FilterTabs";

interface SportsCategoryTabsProps {
  categories: SportsCategoryMeta[];
  activeSlug?: string | null;
  onSelect?: (slug: string | null) => void;
}

export function SportsCategoryTabs({ categories, activeSlug, onSelect }: SportsCategoryTabsProps) {
  if (!categories.length) return null;

  return (
    <FilterTabs
      label="Browse by edge metric"
      hint="Each tab sorts plays differently — Best edge = highest advantage vs the sportsbook."
      allLabel="All plays"
      accent="violet"
      activeId={activeSlug ?? null}
      onSelect={onSelect ?? (() => {})}
      items={categories.map((cat) => ({
        id: cat.slug,
        label: cat.short_label,
        count: cat.count,
        description: cat.description,
      }))}
      guideLinks={categories.map((cat) => ({
        href: `/sports/category/${cat.slug}`,
        label: `${cat.title} guide →`,
      }))}
    />
  );
}
