"use client";

import { FilterTabs } from "@/components/ui/FilterTabs";
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
    <FilterTabs
      label="Filter by league"
      hint="All leagues stay available — sorted by what's in season. Empty tabs mean no +EV play yet; Fetch live odds to refresh."
      allLabel="All leagues"
      accent="violet"
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
