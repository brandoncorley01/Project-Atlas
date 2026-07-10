import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import {
  performanceTrackingForItem,
  type WatchlistItem,
} from "@/lib/watchlist-types";

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

/** Register a saved watchlist pick for performance tracking (idempotent). */
export async function registerPerformanceForItem(item: WatchlistItem): Promise<boolean> {
  const tracking = performanceTrackingForItem(item);
  if (!tracking) return false;

  const token = await getToken();
  if (!usesBffProxy() && !token) return false;

  try {
    const res = await fetch(`${getApiUrl()}/performance`, {
      method: "POST",
      headers: apiRequestHeaders(token),
      credentials: usesBffProxy() ? "include" : "same-origin",
      body: JSON.stringify({
        module: tracking.module,
        signal_id: tracking.signalId,
        outcome: "pending",
        resolution_source: "watchlist",
        signal_snapshot: tracking.signalSnapshot,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
