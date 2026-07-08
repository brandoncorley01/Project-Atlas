import { createClient } from "@/lib/supabase/client";
import type { WatchlistItem, WatchlistItemType } from "@/lib/watchlist-types";
import { effectiveItemType, normalizeWatchlistSymbol } from "@/lib/watchlist-types";

/** Map UI types to DB-safe storage types (legacy schema compatibility). */
function toStoragePayload(payload: {
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

function formatRow(row: Record<string, unknown>): WatchlistItem {
  const item: WatchlistItem = {
    id: String(row.id),
    item_type: String(row.item_type),
    symbol: String(row.symbol),
    metadata: (row.metadata as Record<string, unknown>) ?? {},
    created_at: typeof row.created_at === "string" ? row.created_at : undefined,
  };
  return { ...item, item_type: effectiveItemType(item) };
}

async function ensureDefaultWatchlist(
  supabase: ReturnType<typeof createClient>,
  userId: string,
): Promise<string | null> {
  const { data: existing } = await supabase
    .from("watchlists")
    .select("id")
    .eq("user_id", userId)
    .eq("name", "Default")
    .maybeSingle();

  if (existing?.id) return existing.id;

  const { data: created, error } = await supabase
    .from("watchlists")
    .insert({ user_id: userId, name: "Default" })
    .select("id")
    .single();

  if (error || !created?.id) return null;
  return created.id;
}

export async function fetchWatchlistDirect(): Promise<{
  id: string;
  name: string;
  items: WatchlistItem[];
} | null> {
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.user) return null;

    const watchlistId = await ensureDefaultWatchlist(supabase, session.user.id);
    if (!watchlistId) return null;

    const { data: items, error } = await supabase
      .from("watchlist_items")
      .select("id, item_type, symbol, metadata, created_at")
      .eq("watchlist_id", watchlistId)
      .order("created_at", { ascending: false });

    if (error) return null;

    return {
      id: watchlistId,
      name: "Default",
      items: (items ?? []).map((row) => formatRow(row as Record<string, unknown>)),
    };
  } catch {
    return null;
  }
}

export async function addWatchlistItemDirect(payload: {
  symbol: string;
  item_type: WatchlistItemType;
  metadata?: Record<string, unknown>;
}): Promise<WatchlistItem | null> {
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.user) return null;

    const watchlistId = await ensureDefaultWatchlist(supabase, session.user.id);
    if (!watchlistId) return null;

    const storage = toStoragePayload(payload);

    const { data: existing } = await supabase
      .from("watchlist_items")
      .select("id, item_type, symbol, metadata, created_at")
      .eq("watchlist_id", watchlistId)
      .eq("item_type", storage.item_type)
      .eq("symbol", storage.symbol)
      .maybeSingle();

    if (existing) {
      const { data: updated, error } = await supabase
        .from("watchlist_items")
        .update({ metadata: storage.metadata })
        .eq("id", existing.id)
        .select("id, item_type, symbol, metadata, created_at")
        .single();

      if (error) return formatRow(existing as Record<string, unknown>);
      return formatRow((updated ?? existing) as Record<string, unknown>);
    }

    const { data: saved, error } = await supabase
      .from("watchlist_items")
      .insert({
        watchlist_id: watchlistId,
        user_id: session.user.id,
        item_type: storage.item_type,
        symbol: storage.symbol,
        metadata: storage.metadata,
      })
      .select("id, item_type, symbol, metadata, created_at")
      .single();

    if (error || !saved) return null;
    return formatRow(saved as Record<string, unknown>);
  } catch {
    return null;
  }
}
