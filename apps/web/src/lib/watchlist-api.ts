import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { registerPerformanceForItem } from "@/lib/performance-api";
import { addWatchlistItemDirect, fetchWatchlistDirect } from "@/lib/watchlist-direct";
import type { WatchlistItem, WatchlistItemType } from "@/lib/watchlist-types";
import { normalizeWatchlistItem, normalizeWatchlistSymbol } from "@/lib/watchlist-types";

export { watchlistItemKey } from "@/lib/watchlist-types";

/** Map new item types to legacy API/DB types until migration + API restart are complete. */
function toApiPayload(payload: {
  symbol: string;
  item_type: WatchlistItemType;
  metadata?: Record<string, unknown>;
}): { symbol: string; item_type: string; metadata: Record<string, unknown> } {
  const metadata = { ...(payload.metadata ?? {}), watchlist_kind: payload.item_type };

  switch (payload.item_type) {
    case "sport_bet":
    case "parlay":
      return {
        symbol: normalizeWatchlistSymbol(payload.symbol),
        item_type: "sport_event",
        metadata,
      };
    case "stock_signal":
    case "option_signal":
      return {
        symbol: normalizeWatchlistSymbol(payload.symbol),
        item_type: "ticker",
        metadata,
      };
    default:
      return {
        symbol: normalizeWatchlistSymbol(payload.symbol, payload.item_type),
        item_type: payload.item_type,
        metadata,
      };
  }
}

function normalizeItem(item: WatchlistItem): WatchlistItem {
  return normalizeWatchlistItem({
    id: item.id,
    item_type: String(item.item_type),
    symbol: item.symbol,
    metadata: item.metadata ?? {},
    created_at: item.created_at,
  });
}

function parseApiError(body: unknown, fallback: string): string {
  if (typeof body === "object" && body && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") {
      if (detail.includes("foreign key")) {
        return "Account setup incomplete — sign out and sign in again, then retry.";
      }
      if (detail.includes("check constraint") || detail.includes("item_type_check")) {
        return "Watchlist database needs an update. Saving directly…";
      }
      return detail.length > 240 ? `${detail.slice(0, 240)}…` : detail;
    }
  }
  return fallback;
}

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

function notifyWatchlistUpdated() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("atlas:watchlist-updated"));
  }
}

const watchlistFetchInit = (token?: string): RequestInit => ({
  headers: apiRequestHeaders(token),
  credentials: usesBffProxy() ? "include" : "same-origin",
});

export async function fetchWatchlist(): Promise<{
  id: string;
  name: string;
  items: WatchlistItem[];
} | null> {
  const token = await getToken();
  if (!usesBffProxy() && !token) return null;
  try {
    const res = await fetch(`${getApiUrl()}/watchlist`, watchlistFetchInit(token));
    if (res.ok) {
      const data = await res.json();
      return {
        id: data.id,
        name: data.name,
        items: (data.items as WatchlistItem[]).map(normalizeItem),
      };
    }
  } catch {
    /* fall through to direct Supabase */
  }

  return fetchWatchlistDirect();
}

export async function addWatchlistItem(payload: {
  symbol: string;
  item_type: WatchlistItemType;
  metadata?: Record<string, unknown>;
}): Promise<{ ok: true; item: WatchlistItem } | { ok: false; error: string }> {
  const token = await getToken();
  if (!usesBffProxy() && !token) {
    return { ok: false, error: "Not signed in" };
  }

  const apiPayload = toApiPayload(payload);

  try {
    const res = await fetch(`${getApiUrl()}/watchlist/items`, {
      method: "POST",
      headers: apiRequestHeaders(token),
      credentials: usesBffProxy() ? "include" : "same-origin",
      body: JSON.stringify(apiPayload),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok && body.item) {
      const item = normalizeItem(body.item as WatchlistItem);
      await registerPerformanceForItem(item);
      notifyWatchlistUpdated();
      return { ok: true, item };
    }

    const apiError = parseApiError(body, "Failed to add");
    const direct = await addWatchlistItemDirect(payload);
    if (direct) {
      await registerPerformanceForItem(direct);
      notifyWatchlistUpdated();
      return { ok: true, item: direct };
    }

    return { ok: false, error: apiError };
  } catch {
    const direct = await addWatchlistItemDirect(payload);
    if (direct) {
      await registerPerformanceForItem(direct);
      notifyWatchlistUpdated();
      return { ok: true, item: direct };
    }
    return { ok: false, error: "Backend not responding" };
  }
}

export async function removeWatchlistItem(
  itemId: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/watchlist/items/${itemId}`, {
      method: "DELETE",
      headers: apiRequestHeaders(token),
      credentials: usesBffProxy() ? "include" : "same-origin",
    });
    if (!res.ok) return { ok: false, error: "Failed to remove" };
    notifyWatchlistUpdated();
    return { ok: true };
  } catch {
    return { ok: false, error: "Backend not responding" };
  }
}

export function sportBetMetadata(signal: {
  id: string;
  sport: string;
  event_name: string;
  bet_type: string;
  selection: string;
  odds_american: number;
  opportunity_score?: number;
  expected_value?: number;
  event_start?: string | null;
}) {
  return {
    signal_id: signal.id,
    sport: signal.sport,
    event_name: signal.event_name,
    bet_type: signal.bet_type,
    selection: signal.selection,
    odds_american: signal.odds_american,
    opportunity_score: signal.opportunity_score,
    expected_value: signal.expected_value,
    event_start: signal.event_start,
    label: `${signal.selection} · ${signal.event_name}`,
    watchlist_kind: "sport_bet" as const,
  };
}

export function stockSignalMetadata(signal: {
  id: string;
  ticker: string;
  recommendation: string;
  opportunity_score?: number;
  current_price?: number;
}) {
  return {
    signal_id: signal.id,
    ticker: signal.ticker,
    recommendation: signal.recommendation,
    opportunity_score: signal.opportunity_score,
    current_price: signal.current_price,
    label: `${signal.ticker} — ${signal.recommendation}`,
    watchlist_kind: "stock_signal" as const,
  };
}

export function optionSignalMetadata(signal: {
  id: string;
  underlying: string;
  option_type: string;
  strike: number;
  recommendation: string;
  opportunity_score?: number;
  premium?: number;
  expiration?: string;
}) {
  return {
    signal_id: signal.id,
    underlying: signal.underlying,
    option_type: signal.option_type,
    strike: signal.strike,
    recommendation: signal.recommendation,
    opportunity_score: signal.opportunity_score,
    premium: signal.premium,
    expiration: signal.expiration,
    label: `${signal.underlying} ${signal.option_type.toUpperCase()} $${signal.strike}`,
    watchlist_kind: "option_signal" as const,
  };
}

export function parlayMetadata(parlay: {
  id?: string;
  name?: string | null;
  style?: string;
  combined_odds_american: number;
  combined_odds_decimal: number;
  expected_value?: number;
  confidence_score?: number;
  risk_score?: number;
  opportunity_score?: number;
  correlation_warning?: string | null;
  legs: Array<{
    leg_order: number;
    sport: string;
    event_name: string;
    selection: string;
    bet_type: string;
    odds_american: number;
    sports_signal_id?: string | null;
  }>;
  source?: "auto" | "manual";
  stake?: number;
}) {
  const legKey = parlay.legs.map((l) => l.sports_signal_id ?? l.selection).join("-");
  const symbol =
    parlay.id ??
    `manual-${legKey.slice(0, 24).replace(/[^a-zA-Z0-9-]/g, "")}-${parlay.legs.length}`;

  return {
    symbol,
    metadata: {
      watchlist_kind: "parlay" as const,
      source: parlay.source ?? (parlay.id ? "auto" : "manual"),
      parlay_id: parlay.id ?? null,
      name: parlay.name,
      style: parlay.style,
      combined_odds_american: parlay.combined_odds_american,
      combined_odds_decimal: parlay.combined_odds_decimal,
      expected_value: parlay.expected_value,
      confidence_score: parlay.confidence_score,
      risk_score: parlay.risk_score,
      opportunity_score: parlay.opportunity_score,
      correlation_warning: parlay.correlation_warning,
      legs: parlay.legs,
      stake: parlay.stake ?? 10,
      label: parlay.name ?? `${parlay.legs.length}-leg parlay · ${parlay.combined_odds_american > 0 ? "+" : ""}${parlay.combined_odds_american}`,
    },
  };
}
