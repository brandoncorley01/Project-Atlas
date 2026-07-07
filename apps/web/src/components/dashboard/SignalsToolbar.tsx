"use client";

import type { FilterKey, SortKey } from "@/lib/signal-filters";

interface SignalsToolbarProps {
  sort: SortKey;
  filter: FilterKey;
  onSortChange: (sort: SortKey) => void;
  onFilterChange: (filter: FilterKey) => void;
  resultCount: number;
}

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "win_prob", label: "Win probability" },
  { value: "opportunity", label: "Opportunity score" },
  { value: "risk_low", label: "Lowest risk" },
  { value: "cost_low", label: "Cheapest contract" },
  { value: "dte", label: "Soonest expiration" },
];

const FILTER_OPTIONS: { value: FilterKey; label: string }[] = [
  { value: "all", label: "All picks" },
  { value: "budget", label: "Under $100" },
  { value: "calls", label: "Calls only" },
  { value: "puts", label: "Puts only" },
  { value: "catalyst", label: "News catalyst" },
];

export function SignalsToolbar({
  sort,
  filter,
  onSortChange,
  onFilterChange,
  resultCount,
}: SignalsToolbarProps) {
  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <p className="text-xs text-muted">{resultCount} result{resultCount === 1 ? "" : "s"}</p>
      <div className="flex flex-wrap gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Sort by
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as SortKey)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Filter
          <select
            value={filter}
            onChange={(e) => onFilterChange(e.target.value as FilterKey)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
