"use client";

import { FilterTabs } from "@/components/ui/FilterTabs";
import { buildSportCounts } from "@/lib/sport-meta";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";

interface SportFilterTabsProps {
  items: SportsSignal[];
  activeSport: string | null;
  onSelect: (sport: string | null) => void;
}

export function SportFilterTabs({ items, activeSport, onSelect }: SportFilterTabsProps) {
  const sports = buildSportCounts(items);
  if (sports.length <= 1) return null;

  return (
    <FilterTabs
      label="Filter by league"
      hint="Atlas scans NBA, NFL, MLB, NHL, soccer, MMA, and more — games run 24/7 worldwide."
      allLabel="All leagues"
      accent="violet"
      activeId={activeSport}
      onSelect={onSelect}
      items={sports.map((s) => ({
        id: s.sport,
        label: `${s.meta.emoji} ${s.meta.label}`,
        count: s.count,
      }))}
    />
  );
}
