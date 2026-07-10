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

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Normalize symbols so saved-state keys match API storage (tickers uppercased, UUIDs lowercased). */
export function normalizeWatchlistSymbol(symbol: string, itemType?: string): string {
  const trimmed = symbol.trim();
  if (UUID_RE.test(trimmed)) return trimmed.toLowerCase();
  if (itemType === "ticker") return trimmed.toUpperCase();
  return trimmed;
}

/** Stable key for deduping saved picks across pages. */
export function watchlistItemKey(item: WatchlistItem): string {
  const kind = effectiveItemType(item);
  return `${kind}:${normalizeWatchlistSymbol(item.symbol, kind === "ticker" ? "ticker" : undefined)}`;
}

/** Build a save-state key from button props. */
export function watchlistSaveKey(symbol: string, itemType: string): string {
  return `${itemType}:${normalizeWatchlistSymbol(symbol, itemType === "ticker" ? "ticker" : undefined)}`;
}

/** Map a saved watchlist row to performance tracking ids (null for plain tickers). */
export function performanceTrackingForItem(
  item: WatchlistItem,
): { module: PerformanceModule; signalId: string; signalSnapshot?: Record<string, unknown> } | null {
  const kind = effectiveItemType(item);
  const meta = item.metadata ?? {};

  const snapshot = { ...meta, watchlist_item_id: item.id, symbol: item.symbol };

  const signalFromMetaOrSymbol = (): string | null => {
    if (typeof meta.signal_id === "string" && meta.signal_id.trim()) {
      return normalizeWatchlistSymbol(meta.signal_id);
    }
    if (UUID_RE.test(item.symbol)) {
      return normalizeWatchlistSymbol(item.symbol);
    }
    return null;
  };

  switch (kind) {
    case "sport_bet": {
      const signalId = signalFromMetaOrSymbol();
      return signalId
        ? { module: "sports", signalId, signalSnapshot: snapshot }
        : null;
    }
    case "stock_signal": {
      const signalId = signalFromMetaOrSymbol();
      return signalId
        ? { module: "stock", signalId, signalSnapshot: snapshot }
        : null;
    }
    case "option_signal": {
      const signalId = signalFromMetaOrSymbol();
      return signalId
        ? { module: "options", signalId, signalSnapshot: snapshot }
        : null;
    }
    case "parlay":
      if (typeof meta.parlay_id === "string" && meta.parlay_id.trim()) {
        return {
          module: "parlay",
          signalId: normalizeWatchlistSymbol(meta.parlay_id),
          signalSnapshot: snapshot,
        };
      }
      return { module: "parlay", signalId: normalizeWatchlistSymbol(item.id), signalSnapshot: snapshot };
    default:
      return null;
  }
}

/** Normalize a raw watchlist DB row for UI + performance routing. */
export function normalizeWatchlistItem(row: {
  id: string;
  item_type: string;
  symbol: string;
  metadata?: Record<string, unknown> | null;
  created_at?: string;
}): WatchlistItem {
  const raw: WatchlistItem = {
    id: row.id,
    item_type: row.item_type,
    symbol: row.symbol,
    metadata: row.metadata ?? {},
    created_at: row.created_at,
  };
  const kind = effectiveItemType(raw);
  return {
    ...raw,
    item_type: kind,
    symbol: normalizeWatchlistSymbol(raw.symbol, kind === "ticker" ? "ticker" : undefined),
  };
}
