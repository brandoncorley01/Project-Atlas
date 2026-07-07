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
