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

export async function fetchPerformanceHistory(limit = 200): Promise<PerformanceEntry[]> {
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
  resolutionSource?: string;
  signalSnapshot?: Record<string, unknown>;
}): Promise<PerformanceEntry | null> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/performance`, {
      method: "POST",
      ...fetchInit(token),
      body: JSON.stringify({
        module: params.module,
        signal_id: params.signalId,
        outcome: params.outcome,
        return_pct: params.returnPct,
        resolution_source: params.resolutionSource ?? "manual",
        signal_snapshot: params.signalSnapshot,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok && body.entry) {
      return body.entry as PerformanceEntry;
    }
  } catch {
    /* fall through */
  }
  return logOutcomeDirect({
    module: params.module,
    signalId: params.signalId,
    outcome: params.outcome,
    returnPct: params.returnPct,
    resolutionSource: params.resolutionSource,
    signalSnapshot: params.signalSnapshot,
  });
}

export async function updatePerformanceOutcome(
  outcomeId: string,
  updates: { outcome?: string; returnPct?: number | null },
): Promise<PerformanceEntry | null> {
  const token = await getToken();
  try {
    const body: Record<string, unknown> = {};
    if (updates.outcome) body.outcome = updates.outcome;
    if (updates.returnPct !== undefined) body.return_pct = updates.returnPct;
    const res = await fetch(`${getApiUrl()}/performance/${outcomeId}`, {
      method: "PATCH",
      ...fetchInit(token),
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.entry) {
      return data.entry as PerformanceEntry;
    }
  } catch {
    /* fall through */
  }
  return updateOutcomeDirect(outcomeId, updates);
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

/** Sync all watchlist items into performance tracking. */
export async function syncWatchlistToPerformance(): Promise<{
  synced: number;
  skipped: number;
  total: number;
  source: "api" | "direct";
}> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/performance/sync-watchlist`, {
      method: "POST",
      ...fetchInit(token),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      const result = {
        synced: Number(body.synced ?? 0),
        skipped: Number(body.skipped ?? 0),
        total: Number(body.total ?? 0),
        source: "api" as const,
      };
      if (result.synced > 0) notifyPerformanceUpdated();
      return result;
    }
  } catch {
    /* fall through */
  }

  const direct = await syncWatchlistDirect();
  if (direct.synced > 0) notifyPerformanceUpdated();
  return { ...direct, source: "direct" };
}
