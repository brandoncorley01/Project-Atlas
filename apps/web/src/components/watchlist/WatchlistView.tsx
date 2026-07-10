"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { useWatchlist } from "@/components/watchlist/WatchlistProvider";
import { FilterTabs } from "@/components/ui/FilterTabs";
import { addWatchlistItem, removeWatchlistItem } from "@/lib/watchlist-api";
import {
  effectiveItemType,
  filterWatchlistByTab,
  performanceTrackingForItem,
  watchlistTabCounts,
  type WatchlistItem,
  type WatchlistTab,
} from "@/lib/watchlist-types";

export type { WatchlistItem };

interface WatchlistViewProps {
  initialItems: WatchlistItem[];
  watchlistId: string | null;
}

const TAB_ITEMS = [
  { id: "stocks", label: "Stocks" },
  { id: "options", label: "Options" },
  { id: "bets", label: "Bets" },
  { id: "parlays", label: "Parlays" },
];

function itemTitle(item: WatchlistItem): string {
  const meta = item.metadata ?? {};
  if (typeof meta.label === "string") return meta.label;
  if (item.item_type === "ticker") return item.symbol;
  return item.symbol.slice(0, 8) + "…";
}

function itemSubtitle(item: WatchlistItem): string {
  const meta = item.metadata ?? {};
  switch (effectiveItemType(item)) {
    case "ticker":
      return "Stock ticker · included in scans";
    case "stock_signal":
      return typeof meta.recommendation === "string" ? meta.recommendation : "Stock swing signal";
    case "option_signal":
      return typeof meta.recommendation === "string" ? meta.recommendation : "Options play";
    case "sport_bet":
      return `${meta.bet_type ?? "bet"} · ${meta.event_name ?? ""}`;
    case "parlay": {
      const american =
        typeof meta.combined_odds_american === "number" ? meta.combined_odds_american : null;
      const oddsLabel =
        american != null ? `${american > 0 ? "+" : ""}${american}` : "odds TBD";
      return `${(meta.legs as unknown[])?.length ?? "?"} legs · ${oddsLabel}`;
    }
    default:
      return item.item_type;
  }
}

function itemHref(item: WatchlistItem): string | null {
  const meta = item.metadata ?? {};
  switch (effectiveItemType(item)) {
    case "stock_signal":
      return typeof meta.signal_id === "string" ? `/stocks/${meta.signal_id}` : null;
    case "option_signal":
      return typeof meta.signal_id === "string" ? `/options` : null;
    case "sport_bet":
      return typeof meta.signal_id === "string" ? `/sports/${meta.signal_id}` : null;
    case "parlay":
      if (typeof meta.parlay_id === "string") return `/parlays/${meta.parlay_id}`;
      return null;
    default:
      return item.item_type === "ticker" ? `/stocks` : null;
  }
}

function itemBadge(item: WatchlistItem): string {
  switch (effectiveItemType(item)) {
    case "ticker":
    case "stock_signal":
      return "Stock";
    case "option_signal":
      return "Options";
    case "sport_bet":
      return "Bet";
    case "parlay":
      return "Parlay";
    default:
      return item.item_type;
  }
}

function badgeColor(type: string) {
  if (type === "Stock") return "bg-emerald-500/20 text-emerald-300";
  if (type === "Options") return "bg-sky-500/20 text-sky-300";
  if (type === "Bet") return "bg-violet-500/20 text-violet-300";
  if (type === "Parlay") return "bg-orange-500/20 text-orange-300";
  return "bg-background text-muted";
}

export function WatchlistView({ initialItems, watchlistId }: WatchlistViewProps) {
  const { items, markSaved, markRemoved, loading: watchlistLoading } = useWatchlist();
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get("tab") as WatchlistTab) || "all";
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<WatchlistTab>(
    ["all", "stocks", "options", "bets", "parlays"].includes(initialTab) ? initialTab : "all",
  );

  const displayItems = items.length > 0 ? items : initialItems;
  const counts = useMemo(() => watchlistTabCounts(displayItems), [displayItems]);
  const displayed = useMemo(() => filterWatchlistByTab(displayItems, activeTab), [displayItems, activeTab]);

  async function syncToPerformance() {
    setSyncing(true);
    setMessage(null);
    try {
      const { formatWatchlistSyncMessage, syncWatchlistToPerformance } = await import(
        "@/lib/performance-api"
      );
      const result = await syncWatchlistToPerformance();
      setMessage(formatWatchlistSyncMessage(result));
      window.dispatchEvent(new Event("atlas:performance-updated"));
      window.dispatchEvent(new Event("atlas:watchlist-updated"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not sync watchlist");
    }
    setSyncing(false);
  }

  async function addTicker(e: React.FormEvent) {
    e.preventDefault();
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setMessage(null);
    const result = await addWatchlistItem({ symbol: sym, item_type: "ticker" });
    if (result.ok) {
      markSaved(result.item);
      setSymbol("");
      setMessage(`Added ${sym}`);
    } else {
      setMessage(result.error);
    }
    setLoading(false);
  }

  async function removeItem(id: string) {
    setLoading(true);
    const result = await removeWatchlistItem(id);
    if (result.ok) {
      markRemoved(id);
    } else {
      setMessage(result.error);
    }
    setLoading(false);
  }

  return (
    <div>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {(
          [
            ["all", "All picks", counts.all],
            ["stocks", "Stocks", counts.stocks],
            ["options", "Options", counts.options],
            ["bets", "Bets", counts.bets],
            ["parlays", "Parlays", counts.parlays],
          ] as const
        ).map(([id, label, count]) => (
          <div
            key={id}
            className="rounded-lg border border-border bg-surface-elevated px-3 py-2 text-center"
          >
            <p className="text-lg font-bold">{count}</p>
            <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
          </div>
        ))}
      </div>

      <FilterTabs
        label="Filter by type"
        hint="Everything you save from Sports, Parlays, Options, and Stocks lands here and is tracked in Performance."
        allLabel="All"
        items={TAB_ITEMS.map((t) => ({ id: t.id, label: t.label, count: counts[t.id as WatchlistTab] }))}
        activeId={activeTab === "all" ? null : activeTab}
        onSelect={(id) => setActiveTab((id ?? "all") as WatchlistTab)}
        accent="accent"
        guideLinks={[
          { href: "/sports", label: "Build a manual parlay on Sports →" },
          { href: "/parlays", label: "Save auto-built parlays →" },
          { href: "/performance", label: "View performance tracking →" },
        ]}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void syncToPerformance()}
          disabled={syncing || loading || displayItems.length === 0}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {syncing ? "Syncing…" : "Sync to Performance"}
        </button>
        <Link
          href="/performance"
          className="rounded-lg border border-border px-3 py-2 text-sm text-muted hover:text-foreground"
        >
          Open Performance →
        </Link>
        <p className="text-xs text-muted">
          Pushes saved bets, stocks, options, and parlays into Performance for grading.
        </p>
      </div>

      {(activeTab === "all" || activeTab === "stocks") && (
        <form onSubmit={addTicker} className="mb-6 flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Add stock ticker (e.g. AAPL)"
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={loading || watchlistLoading || !symbol.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? "Adding…" : "Add ticker"}
          </button>
        </form>
      )}

      {message && <p className="mb-4 text-sm text-muted">{message}</p>}

      {watchlistId && activeTab === "stocks" && (
        <p className="mb-3 text-xs text-muted">
          Tickers are auto-included in options and stock scans.
        </p>
      )}

      {displayed.length > 0 ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {displayed.map((item) => {
            const href = itemHref(item);
            const badge = itemBadge(item);
            const meta = item.metadata ?? {};
            const tracking = performanceTrackingForItem(item);
            return (
              <li key={item.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${badgeColor(badge)}`}>
                      {badge}
                    </span>
                    {href ? (
                      <Link href={href} className="font-medium hover:text-accent">
                        {itemTitle(item)}
                      </Link>
                    ) : (
                      <span className="font-medium">{itemTitle(item)}</span>
                    )}
                    {tracking && (
                      <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent">
                        Tracking
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-sm text-muted">{itemSubtitle(item)}</p>
                  {effectiveItemType(item) === "parlay" && Array.isArray(meta.legs) && (
                    <ul className="mt-2 space-y-0.5 text-xs text-muted">
                      {(meta.legs as Array<{ selection?: string; odds_american?: number }>)
                        .slice(0, 4)
                        .map((leg, i) => (
                          <li key={i}>
                            {leg.selection}
                            {leg.odds_american != null && (
                              <span className="ml-1 text-fanduel-text">
                                {leg.odds_american > 0 ? "+" : ""}
                                {leg.odds_american}
                              </span>
                            )}
                          </li>
                        ))}
                    </ul>
                  )}
                  {meta.opportunity_score != null && (
                    <p className="mt-1 text-xs text-muted">
                      Opportunity {Number(meta.opportunity_score).toFixed(0)}
                    </p>
                  )}
                  {tracking && (
                    <div className="mt-3 rounded-lg border border-border/60 bg-surface-elevated p-3">
                      <LogOutcomeButtons
                        module={tracking.module}
                        signalId={tracking.signalId}
                        signalSnapshot={tracking.signalSnapshot}
                        compact
                      />
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeItem(item.id)}
                  disabled={loading}
                  className="shrink-0 self-start text-xs text-muted hover:text-danger"
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
          <p className="font-medium text-foreground">No {activeTab === "all" ? "" : activeTab} saved yet</p>
          <p className="mt-2 text-sm">
            Save plays from{" "}
            <Link href="/sports" className="text-accent hover:underline">
              Sports
            </Link>
            ,{" "}
            <Link href="/parlays" className="text-accent hover:underline">
              Parlays
            </Link>
            ,{" "}
            <Link href="/options" className="text-accent hover:underline">
              Options
            </Link>
            , or{" "}
            <Link href="/stocks" className="text-accent hover:underline">
              Stocks
            </Link>
            . Saved picks are tracked in{" "}
            <Link href="/performance" className="text-accent hover:underline">
              Performance
            </Link>
            .
          </p>
        </div>
      )}
    </div>
  );
}
