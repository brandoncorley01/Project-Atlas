"use client";

import type { SportsCategoryMeta } from "@/lib/sports-categories";
import { FilterSelect } from "@/components/ui/FilterSelect";

interface SportsCategoryTabsProps {
  categories: SportsCategoryMeta[];
  activeSlug?: string | null;
  onSelect?: (slug: string | null) => void;
}

export function SportsCategoryTabs({ categories, activeSlug, onSelect }: SportsCategoryTabsProps) {
  if (!categories.length) return null;

  return (
    <FilterSelect
      label="Browse by edge metric"
      hint="Insight & Props keep Atlas player markets visible. Best edge ranks Odds-API edges."
      allLabel="All plays"
      activeId={activeSlug ?? null}
      onSelect={onSelect ?? (() => {})}
      items={categories.map((cat) => ({
        id: cat.slug,
        label: cat.short_label || cat.title,
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
