import type { PerformanceEntry, PerformanceSummary } from "@/components/performance/PerformanceView";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import {
  backfillTrackingDirect,
  computeSummaryDirect,
  fetchPerformanceHistoryDirect,
  getOutcomeDirect,
  logOutcomeDirect,
  syncWatchlistDirect,
  updateOutcomeDirect,
} from "@/lib/performance-direct";
import {
  performanceTrackingForItem,
  type WatchlistItem,
} from "@/lib/watchlist-types";

export interface WatchlistSyncResult {
  synced: number;
  skipped: number;
  alreadyTracked: number;
  total: number;
  trackable: number;
  errors: string[];
  source: "api" | "direct";
}

function notifyPerformanceUpdated() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("atlas:performance-updated"));
  }
}

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

const fetchInit = (token?: string): RequestInit => ({
  headers: apiRequestHeaders(token),
  credentials: usesBffProxy() ? "include" : "same-origin",
});

export async function fetchPerformanceHistory(limit = 1000): Promise<PerformanceEntry[]> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/performance/history?limit=${limit}`, {
      ...fetchInit(token),
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json();
      return data.items ?? [];
    }
  } catch {
    /* fall through */
  }
  return fetchPerformanceHistoryDirect(limit);
}

export async function fetchPerformanceSummary(days = 30): Promise<PerformanceSummary> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/performance/summary?days=${days}`, {
      ...fetchInit(token),
      cache: "no-store",
    });
    if (res.ok) {
      return (await res.json()) as PerformanceSummary;
    }
  } catch {
    /* fall through */
  }
  const history = await fetchPerformanceHistoryDirect(500);
  return computeSummaryDirect(history, days);
}

export async function getPerformanceOutcome(
  module: string,
  signalId: string,
): Promise<PerformanceEntry | null> {
  const token = await getToken();
  try {
    const params = new URLSearchParams({ module, signal_id: signalId });
    const res = await fetch(`${getApiUrl()}/performance/outcome?${params}`, fetchInit(token));
    if (res.ok) {
      const data = await res.json();
      return data.outcome ?? null;
    }
  } catch {
    /* fall through */
  }
  return getOutcomeDirect(module, signalId);
}

export async function logPerformanceOutcome(params: {
  module: string;
  signalId: string;
  outcome: string;
  returnPct?: number | null;
  holdDurationHours?: number | null;
  resolutionSource?: string;
  signalSnapshot?: Record<string, unknown>;
}): Promise<PerformanceEntry | null> {
  const token = await getToken();
  let saved: PerformanceEntry | null = null;
  try {
    const res = await fetch(`${getApiUrl()}/performance`, {
      method: "POST",
      ...fetchInit(token),
      body: JSON.stringify({
        module: params.module,
        signal_id: params.signalId,
        outcome: params.outcome,
        return_pct: params.returnPct,
        hold_duration_hours: params.holdDurationHours,
        resolution_source: params.resolutionSource ?? "manual",
        signal_snapshot: params.signalSnapshot,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok && body.entry) {
      saved = body.entry as PerformanceEntry;
    }
  } catch {
    /* fall through */
  }
  if (!saved) {
    saved = await logOutcomeDirect({
      module: params.module,
      signalId: params.signalId,
      outcome: params.outcome,
      returnPct: params.returnPct,
      holdDurationHours: params.holdDurationHours,
      resolutionSource: params.resolutionSource,
      signalSnapshot: params.signalSnapshot,
    });
  }
  if (saved && params.outcome !== "pending") {
    notifyPerformanceUpdated();
    void syncAtlasLearningAfterOutcome();
  }
  return saved;
}

export async function updatePerformanceOutcome(
  outcomeId: string,
  updates: {
    outcome?: string;
    returnPct?: number | null;
    holdDurationHours?: number | null;
  },
): Promise<PerformanceEntry | null> {
  const token = await getToken();
  let saved: PerformanceEntry | null = null;
  try {
    const body: Record<string, unknown> = {};
    if (updates.outcome) body.outcome = updates.outcome;
    if (updates.returnPct !== undefined) body.return_pct = updates.returnPct;
    if (updates.holdDurationHours !== undefined) {
      body.hold_duration_hours = updates.holdDurationHours;
    }
    const res = await fetch(`${getApiUrl()}/performance/${outcomeId}`, {
      method: "PATCH",
      ...fetchInit(token),
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.entry) {
      saved = data.entry as PerformanceEntry;
    }
  } catch {
    /* fall through */
  }
  if (!saved) {
    saved = await updateOutcomeDirect(outcomeId, updates);
  }
  if (saved) {
    notifyPerformanceUpdated();
    void syncAtlasLearningAfterOutcome();
  }
  return saved;
}

/**
 * Push a newly saved / changed result into Atlas's learning rollup so the next
 * sports/stocks/options scans and coach insight use the updated win/loss data.
 */
let learningSyncInFlight: Promise<{ ok: boolean; message: string }> | null = null;
let learningSyncTimer: number | null = null;

export async function syncAtlasLearningAfterOutcome(): Promise<{
  ok: boolean;
  message: string;
}> {
  if (learningSyncInFlight) return learningSyncInFlight;

  learningSyncInFlight = (async () => {
    if (typeof window !== "undefined") {
      await new Promise<void>((resolve) => {
        if (learningSyncTimer) window.clearTimeout(learningSyncTimer);
        learningSyncTimer = window.setTimeout(() => resolve(), 150);
      });
    }
    const token = await getToken();
    try {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 20_000);
      const res = await fetch(`${getApiUrl()}/engine/coach-aggregate`, {
        method: "POST",
        ...fetchInit(token),
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("atlas:learning-updated"));
        }
        return {
          ok: true,
          message: "Saved — Atlas learning updated from this result.",
        };
      }
      return {
        ok: false,
        message:
          typeof body.detail === "string"
            ? body.detail
            : "Result saved — learning sync will catch up on the next scan.",
      };
    } catch {
      return {
        ok: false,
        message: "Result saved — learning sync will catch up on the next scan.",
      };
    } finally {
      learningSyncInFlight = null;
      learningSyncTimer = null;
    }
  })();

  return learningSyncInFlight;
}

export async function backfillPerformanceTracking(): Promise<{
  registered: number;
  skipped: number;
  by_module: Record<string, { registered: number; skipped?: number }>;
  source: "api" | "direct";
}> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/ai/backfill-tracking`, {
      method: "POST",
      ...fetchInit(token),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      return {
        registered: Number(body.registered ?? 0),
        skipped: Number(body.skipped ?? 0),
        by_module: body.by_module ?? {},
        source: "api",
      };
    }
  } catch {
    /* fall through */
  }
  const direct = await backfillTrackingDirect();
  return { ...direct, source: "direct" };
}

/** Register a saved watchlist pick for performance tracking (idempotent). */
export async function registerPerformanceForItem(
  item: WatchlistItem,
  options?: { notify?: boolean },
): Promise<boolean> {
  const tracking = performanceTrackingForItem(item);
  if (!tracking) return false;
  try {
    const entry = await logPerformanceOutcome({
      module: tracking.module,
      signalId: tracking.signalId,
      outcome: "pending",
      resolutionSource: "watchlist",
      signalSnapshot: tracking.signalSnapshot,
    });
    if (entry && options?.notify !== false) {
      notifyPerformanceUpdated();
    }
    return entry != null;
  } catch {
    return false;
  }
}

/** Sync all watchlist items into performance tracking (direct Supabase, API fallback). */
export async function syncWatchlistToPerformance(): Promise<WatchlistSyncResult> {
  const direct = await syncWatchlistDirect();

  // Direct is done when: empty list, newly synced rows, or every trackable pick already exists.
  const directDone =
    direct.total === 0 ||
    direct.synced > 0 ||
    (direct.trackable > 0 &&
      direct.alreadyTracked >= direct.trackable &&
      direct.errors.length === 0);

  if (directDone) {
    if (direct.synced > 0 || direct.alreadyTracked > 0) notifyPerformanceUpdated();
    return { ...direct, source: "direct" };
  }

  // Direct failed or couldn't track — try the API bridge.
  const token = await getToken();
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 25_000);
    const res = await fetch(`${getApiUrl()}/performance/sync-watchlist`, {
      method: "POST",
      ...fetchInit(token),
      signal: controller.signal,
    });
    window.clearTimeout(timeout);
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      const synced = Number(body.synced ?? body.registered ?? 0);
      const alreadyTracked = Number(body.already_tracked ?? body.alreadyTracked ?? 0);
      const skipped = Number(body.skipped ?? 0);
      const total = Number(body.total ?? body.total_items ?? 0);
      const result: WatchlistSyncResult = {
        synced,
        skipped,
        alreadyTracked,
        total,
        trackable: synced + alreadyTracked,
        errors: Array.isArray(body.errors) ? body.errors.map(String) : [],
        source: "api",
      };
      if (body.trackable != null) result.trackable = Number(body.trackable);
      if (synced > 0 || alreadyTracked > 0) notifyPerformanceUpdated();
      return result;
    }
  } catch {
    /* fall through to direct result */
  }

  if (direct.alreadyTracked > 0 || direct.synced > 0) notifyPerformanceUpdated();
  return { ...direct, source: "direct" };
}

/** User-facing message for a watchlist sync result. */
export function formatWatchlistSyncMessage(result: WatchlistSyncResult): string {
  if (result.errors.length > 0 && result.synced === 0 && result.alreadyTracked === 0) {
    if (result.total === 0) {
      return result.errors[0] ?? "Could not read watchlist";
    }
    return `Sync failed: ${result.errors[0]}`;
  }
  if (result.total === 0) {
    return "No picks on your watchlist yet — save plays from Sports, Stocks, or Options first.";
  }
  if (result.trackable === 0) {
    return "Watchlist has items but none are trackable picks (plain tickers are scan-only).";
  }
  if (result.synced > 0) {
    const via = result.source === "direct" ? " via Supabase" : "";
    const already =
      result.alreadyTracked > 0 ? ` · ${result.alreadyTracked} already tracked` : "";
    return `Synced ${result.synced} watchlist pick(s) to performance${via}${already}.`;
  }
  if (result.alreadyTracked > 0) {
    return `All ${result.alreadyTracked} trackable watchlist pick(s) are already in performance.`;
  }
  if (result.errors.length > 0) {
    return `Sync failed: ${result.errors[0]}`;
  }
  return "Could not sync watchlist picks — try Register all past picks.";
}
