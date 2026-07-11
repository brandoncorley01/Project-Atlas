"use client";

import { useCallback, useEffect, useState } from "react";
import { usesBffProxy } from "@/lib/api-url";
import { resolveOddsTotalCredits } from "@/lib/odds-credits";
import {
  fetchOddsProviderStatus,
  rescoreButtonLabel,
  type OddsApiStatus,
} from "@/lib/odds-status";

export type { OddsApiStatus };

export function useOddsApiStatus() {
  const [status, setStatus] = useState<OddsApiStatus | null>(null);

  const refresh = useCallback(async () => {
    let token: string | undefined;
    if (!usesBffProxy()) {
      const { createClient } = await import("@/lib/supabase/client");
      const { data } = await createClient().auth.getSession();
      token = data.session?.access_token ?? undefined;
    }
    try {
      const oddsData = await fetchOddsProviderStatus(token);
      setStatus(oddsData);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onRefresh = () => void refresh();
    window.addEventListener("atlas:dashboard-refresh", onRefresh);
    window.addEventListener("focus", onRefresh);
    const interval = window.setInterval(() => void refresh(), 90_000);
    return () => {
      window.removeEventListener("atlas:dashboard-refresh", onRefresh);
      window.removeEventListener("focus", onRefresh);
      window.clearInterval(interval);
    };
  }, [refresh]);

  return { status, refresh };
}

export { rescoreButtonLabel };

export function OddsQuotaBanner({ status }: { status: OddsApiStatus | null }) {
  if (!status?.configured) return null;

  const remaining = resolveOddsTotalCredits(status);
  const keyCount = status.key_count ?? status.keys?.length ?? 1;
  const capacity = status.monthly_capacity ?? keyCount * 500;
  const estimate = status.estimated_live_scan_credits ?? 12;

  return (
    <div
      className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
        status.cache_rescore_free
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <p className="font-medium text-foreground">Credit conservation</p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">
        {remaining != null ? (
          <>
            <strong className="text-foreground">{remaining.toLocaleString()}</strong> of{" "}
            {capacity.toLocaleString()} credits left across {keyCount} key{keyCount === 1 ? "" : "s"}.
          </>
        ) : (
          <>Checking Odds API quota…</>
        )}{" "}
        {status.cache_rescore_free ? (
          <>
            Cached odds are warm — <strong className="text-emerald-400">{rescoreButtonLabel(status)}</strong>{" "}
            costs 0 credits. Prefer that over Fetch. OpenAI explains picks from cache; it does not invent odds.
          </>
        ) : (
          <>
            Cache is cold — <strong className="text-amber-300">Fetch live odds</strong> uses ~
            {estimate} credits (in-season leagues only). OpenAI fills insight gaps after lines are cached.
          </>
        )}
      </p>
      {status.error && <p className="mt-2 text-xs text-amber-300">{status.error}</p>}
    </div>
  );
}
