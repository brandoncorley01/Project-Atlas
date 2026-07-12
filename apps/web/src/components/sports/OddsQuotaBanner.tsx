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
  const estimate = status.estimated_live_scan_credits ?? 4;
  const locked = Boolean(status.spend_locked || status.live_fetch_allowed === false);
  const exhausted = Boolean(status.quota_exhausted) || (remaining != null && remaining <= 0);

  return (
    <div
      className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
        locked || exhausted
          ? "border-sky-500/40 bg-sky-500/10"
          : status.cache_rescore_free
            ? "border-emerald-500/30 bg-emerald-500/5"
            : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <p className="font-medium text-foreground">
        {locked || exhausted ? "Zero-credit mode (Odds locked)" : "Credit conservation"}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">
        {remaining != null ? (
          <>
            <strong className="text-foreground">{remaining.toLocaleString()}</strong> of{" "}
            {capacity.toLocaleString()} credits left across {keyCount} key
            {keyCount === 1 ? "" : "s"}.{" "}
          </>
        ) : (
          <>Checking Odds API quota… </>
        )}
        {locked || exhausted ? (
          <>
            Live Fetch is blocked. Use <strong className="text-emerald-300">Rescore</strong> on
            cached lines (0 credits), <strong className="text-sky-300">Atlas Insight</strong>{" "}
            (OpenAI + cache), and Search — no Odds spend. Add new free keys later, then set{" "}
            <code className="text-foreground">ODDS_SPEND_MODE=conservative</code> on Render.
          </>
        ) : status.cache_rescore_free ? (
          <>
            Cached odds are warm — <strong className="text-emerald-400">Rescore</strong> costs 0
            Odds credits. Prefer that over Fetch. Use{" "}
            <strong className="text-sky-300">Atlas Insight</strong> for analyst consensus without
            Odds credits.
          </>
        ) : (
          <>
            Cache is cold — <strong className="text-amber-300">Fetch live odds</strong> uses ~
            {estimate} credits. Then <strong className="text-sky-300">Atlas Insight</strong>{" "}
            ranks FanDuel-verified props & lines.
          </>
        )}
      </p>
      {status.error && <p className="mt-2 text-xs text-amber-300">{status.error}</p>}
    </div>
  );
}
