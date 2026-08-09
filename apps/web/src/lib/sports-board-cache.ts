/**
 * Persist Sports board across client navigations so picks don't vanish on remount.
 * sessionStorage is per-tab and cleared when the tab closes — intentional.
 */

import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import { dedupeOneSidePerMarket } from "@/lib/sports-filters";

const STORAGE_KEY = "atlas.sports.board.v1";

export interface SportsBoardCache {
  items: SportsSignal[];
  savedAt: string;
  /** Last successful Scan / Fetch / Rescore / Atlas Insight from this browser. */
  lastActionAt?: string | null;
  lastActionKind?: "scan" | "live" | "rescore" | "openai" | null;
  /** Max pick data_as_of from the board when saved. */
  boardAsOf?: string | null;
  oddsFetchedAt?: string | null;
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof sessionStorage !== "undefined";
}

export function boardAsOfFromItems(items: SportsSignal[]): string | null {
  let best: string | null = null;
  let bestMs = 0;
  for (const row of items) {
    const raw = row.data_as_of ?? null;
    if (typeof raw !== "string" || !raw) continue;
    const ms = Date.parse(raw);
    if (!Number.isFinite(ms)) continue;
    if (ms >= bestMs) {
      bestMs = ms;
      best = raw;
    }
  }
  return best;
}

export function readSportsBoardCache(): SportsBoardCache | null {
  if (!canUseStorage()) return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SportsBoardCache;
    if (!parsed || !Array.isArray(parsed.items)) return null;
    return {
      ...parsed,
      items: dedupeOneSidePerMarket(parsed.items),
    };
  } catch {
    return null;
  }
}

export function writeSportsBoardCache(
  items: SportsSignal[],
  extras?: Partial<Omit<SportsBoardCache, "items" | "savedAt">>,
): void {
  if (!canUseStorage()) return;
  const prev = readSportsBoardCache();
  const payload: SportsBoardCache = {
    items: dedupeOneSidePerMarket(items),
    savedAt: new Date().toISOString(),
    lastActionAt: extras?.lastActionAt ?? prev?.lastActionAt ?? null,
    lastActionKind: extras?.lastActionKind ?? prev?.lastActionKind ?? null,
    boardAsOf: extras?.boardAsOf ?? boardAsOfFromItems(items) ?? prev?.boardAsOf ?? null,
    oddsFetchedAt: extras?.oddsFetchedAt ?? prev?.oddsFetchedAt ?? null,
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Quota / private mode — ignore.
  }
}

export function markSportsBoardAction(
  kind: NonNullable<SportsBoardCache["lastActionKind"]>,
): void {
  if (!canUseStorage()) return;
  const prev = readSportsBoardCache();
  writeSportsBoardCache(prev?.items ?? [], {
    lastActionAt: new Date().toISOString(),
    lastActionKind: kind,
    boardAsOf: prev?.boardAsOf,
    oddsFetchedAt: prev?.oddsFetchedAt,
  });
}

export function hydrateSportsItems(initialItems: SportsSignal[]): SportsSignal[] {
  const fromServer = dedupeOneSidePerMarket(initialItems);
  if (fromServer.length > 0) {
    writeSportsBoardCache(fromServer, { boardAsOf: boardAsOfFromItems(fromServer) });
    return fromServer;
  }
  const cached = readSportsBoardCache();
  return cached?.items?.length ? cached.items : [];
}

/** Relative label like "3m ago" / "2h ago". */
export function formatRelativeAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  const minutes = Math.max(0, Math.round((Date.now() - ms) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function formatClockLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
