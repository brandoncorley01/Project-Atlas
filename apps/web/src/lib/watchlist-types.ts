export type WatchlistItemType =
  | "ticker"
  | "sport_event"
  | "team"
  | "sport_bet"
  | "parlay"
  | "stock_signal"
  | "option_signal";

export type WatchlistTab = "all" | "stocks" | "options" | "bets" | "parlays";

export interface WatchlistItem {
  id: string;
  item_type: WatchlistItemType | string;
  symbol: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

/** Logical type for UI tabs — reads watchlist_kind when stored as legacy sport_event/ticker. */
export function effectiveItemType(item: WatchlistItem): WatchlistItemType | string {
  const kind = item.metadata?.watchlist_kind;
  if (typeof kind === "string") return kind;

  const meta = item.metadata ?? {};
  if (item.item_type === "sport_event") {
    if (Array.isArray(meta.legs)) return "parlay";
    if (meta.bet_type || meta.signal_id) return "sport_bet";
  }
  if (item.item_type === "ticker") {
    if (meta.signal_id && meta.underlying) return "option_signal";
    if (meta.signal_id && meta.ticker) return "stock_signal";
  }
  return item.item_type;
}

export const WATCHLIST_TAB_TYPES: Record<WatchlistTab, WatchlistItemType[] | null> = {
  all: null,
  stocks: ["ticker", "stock_signal"],
  options: ["option_signal"],
  bets: ["sport_bet"],
  parlays: ["parlay"],
};

export function filterWatchlistByTab(items: WatchlistItem[], tab: WatchlistTab): WatchlistItem[] {
  const types = WATCHLIST_TAB_TYPES[tab];
  if (!types) return items;
  return items.filter((i) => types.includes(effectiveItemType(i) as WatchlistItemType));
}

export function watchlistTabCounts(items: WatchlistItem[]): Record<WatchlistTab, number> {
  return {
    all: items.length,
    stocks: filterWatchlistByTab(items, "stocks").length,
    options: filterWatchlistByTab(items, "options").length,
    bets: filterWatchlistByTab(items, "bets").length,
    parlays: filterWatchlistByTab(items, "parlays").length,
  };
}

export type PerformanceModule = "options" | "stock" | "sports" | "parlay";

/** Stable key for deduping saved picks across pages. */
export function watchlistItemKey(item: WatchlistItem): string {
  return `${effectiveItemType(item)}:${item.symbol}`;
}

/** Map a saved watchlist row to performance tracking ids (null for plain tickers). */
export function performanceTrackingForItem(
  item: WatchlistItem,
): { module: PerformanceModule; signalId: string } | null {
  const kind = effectiveItemType(item);
  const meta = item.metadata ?? {};

  switch (kind) {
    case "sport_bet":
      return typeof meta.signal_id === "string"
        ? { module: "sports", signalId: meta.signal_id }
        : null;
    case "stock_signal":
      return typeof meta.signal_id === "string"
        ? { module: "stock", signalId: meta.signal_id }
        : null;
    case "option_signal":
      return typeof meta.signal_id === "string"
        ? { module: "options", signalId: meta.signal_id }
        : null;
    case "parlay":
      if (typeof meta.parlay_id === "string") {
        return { module: "parlay", signalId: meta.parlay_id };
      }
      return { module: "parlay", signalId: item.id };
    default:
      return null;
  }
}
