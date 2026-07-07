"use client";

import type { ParlayStyleMeta } from "@/lib/parlay-styles";
import { emptyParlayStyleCatalog } from "@/lib/parlay-styles";
import { FilterTabs } from "@/components/ui/FilterTabs";

interface ParlayStyleTabsProps {
  styles?: ParlayStyleMeta[];
  activeSlug?: string | null;
  onSelect?: (slug: string | null) => void;
}

const STYLE_ACCENTS: Record<string, "emerald" | "sky" | "orange"> = {
  conservative: "emerald",
  balanced: "sky",
  aggressive: "orange",
};

export function ParlayStyleTabs({
  styles,
  activeSlug,
  onSelect,
}: ParlayStyleTabsProps) {
  const tabs = styles?.length ? styles : emptyParlayStyleCatalog();
  const activeAccent = activeSlug ? (STYLE_ACCENTS[activeSlug] ?? "accent") : "accent";

  return (
    <FilterTabs
      label="Risk tier — how many legs?"
      hint="More legs = bigger payout if you win, but harder to hit. Start with Conservative if you're new."
      allLabel="All tiers"
      accent={activeAccent as "emerald" | "sky" | "orange" | "accent"}
      activeId={activeSlug ?? null}
      onSelect={onSelect ?? (() => {})}
      items={tabs.map((style) => ({
        id: style.slug,
        label: style.short_label,
        count: style.count,
        description: style.description,
      }))}
    />
  );
}
