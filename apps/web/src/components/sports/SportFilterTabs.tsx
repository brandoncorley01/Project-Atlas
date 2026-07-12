"use client";

import { FilterSelect } from "@/components/ui/FilterSelect";
import { buildLeagueCatalog } from "@/lib/sport-meta";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";

interface SportFilterTabsProps {
  items: SportsSignal[];
  activeSport: string | null;
  onSelect: (sport: string | null) => void;
  extraLeagues?: string[];
}

export function SportFilterTabs({
  items,
  activeSport,
  onSelect,
  extraLeagues = [],
}: SportFilterTabsProps) {
  const sports = buildLeagueCatalog(items, extraLeagues);
  if (sports.length === 0) return null;

  return (
    <FilterSelect
      label="Filter by league"
      hint="All leagues stay available. Counts include Atlas Insight props after you run Insight."
      allLabel="All leagues"
      activeId={activeSport}
      onSelect={onSelect}
      items={sports.map((s) => ({
        id: s.sport,
        label: `${s.meta.emoji} ${s.meta.label}`,
        count: s.count,
        description:
          s.count > 0
            ? `${s.count} play${s.count === 1 ? "" : "s"}`
            : "No +EV plays yet — still available to browse after the next scan",
      }))}
    />
  );
}
