"use client";

import type { SportsSortKey, SportsFilterKey, SportsWindowKey } from "@/lib/sports-filters";
import { TermHint } from "@/components/ui/TermHint";

interface SportsToolbarProps {
  sort: SportsSortKey;
  filter: SportsFilterKey;
  window: SportsWindowKey;
  onSortChange: (sort: SportsSortKey) => void;
  onFilterChange: (filter: SportsFilterKey) => void;
  onWindowChange: (window: SportsWindowKey) => void;
  resultCount: number;
}

const SORT_OPTIONS: { value: SportsSortKey; label: string }[] = [
  { value: "soonest", label: "Starting soonest" },
  { value: "opportunity", label: "Best overall" },
  { value: "openai", label: "OpenAI picks first" },
  { value: "edge", label: "Highest edge" },
  { value: "ev", label: "Highest EV" },
  { value: "confidence", label: "Most confident" },
  { value: "risk_low", label: "Safest" },
];

const FILTER_OPTIONS: { value: SportsFilterKey; label: string }[] = [
  { value: "all", label: "All bet types" },
  { value: "openai", label: "OpenAI picks" },
  { value: "moneyline", label: "Moneyline" },
  { value: "spread", label: "Spread" },
  { value: "total", label: "Over/Under" },
  { value: "futures", label: "Futures" },
  { value: "steam", label: "Steam moves" },
  { value: "value", label: "Value plays" },
];

const WINDOW_OPTIONS: { value: SportsWindowKey; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "soon", label: "Next 48h" },
  { value: "week", label: "This week" },
  { value: "month", label: "Next 30 days" },
  { value: "futures", label: "Futures & long odds" },
  { value: "all", label: "All dates" },
];

function windowHint(window: SportsWindowKey): string {
  switch (window) {
    case "today":
      return "today (Eastern)";
    case "soon":
      return "next 48 hours";
    case "week":
      return "this week";
    case "month":
      return "next 30 days";
    case "futures":
      return "futures & longer-dated lines";
    default:
      return "all dates";
  }
}

export function SportsToolbar({
  sort,
  filter,
  window,
  onSortChange,
  onFilterChange,
  onWindowChange,
  resultCount,
}: SportsToolbarProps) {
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-xl border border-violet-500/25 bg-violet-500/5 p-4 sm:flex-row sm:items-end sm:justify-between">
      <p className="text-sm text-muted">
        <strong className="text-foreground">{resultCount}</strong> play{resultCount === 1 ? "" : "s"}{" "}
        · {windowHint(window)} · sort favors{" "}
        <TermHint term="opportunity" className="text-muted" />
      </p>
      <div className="flex flex-wrap gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Window
          <select
            value={window}
            onChange={(e) => onWindowChange(e.target.value as SportsWindowKey)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-violet-500"
          >
            {WINDOW_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Sort by
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as SportsSortKey)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-violet-500"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Bet type
          <select
            value={filter}
            onChange={(e) => onFilterChange(e.target.value as SportsFilterKey)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-violet-500"
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
