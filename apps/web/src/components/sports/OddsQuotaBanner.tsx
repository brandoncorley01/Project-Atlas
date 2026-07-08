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
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    const interval = window.setInterval(() => void refresh(), 90_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(interval);
    };
  }, [refresh]);

  return { status, refresh };
}

export { rescoreButtonLabel };

export function OddsQuotaBanner({ status }: { status: OddsApiStatus | null }) {
  if (!status?.configured) return null;

  const fresh = status.cache_fresh;
  const needsLive = status.cache_needs_live_refresh;
  const rescoreFree = status.cache_rescore_free;
  const age = status.cache_age_minutes;
  const nearLeagues = status.near_term_leagues ?? [];
  const remaining = resolveOddsTotalCredits(status);
  const estimate = status.estimated_live_scan_credits ?? 13;
  const scope = status.scan_scope === "full" ? "all leagues" : "priority leagues";

  return (
    <div
      className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
        fresh
          ? "border-emerald-500/30 bg-emerald-500/5"
          : rescoreFree
            ? "border-violet-500/40 bg-violet-500/10"
            : needsLive
              ? "border-violet-500/40 bg-violet-500/10"
              : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <p className="font-medium text-foreground">Odds API quota conservation</p>
      <ul className="mt-2 space-y-1 text-xs text-muted">
        {rescoreFree && age != null ? (
          <li>
            Saved odds are <strong className="text-foreground">{Math.round(age)}m old</strong> — tap{" "}
            <strong className="text-emerald-400">{rescoreButtonLabel(status)}</strong> to re-rank at{" "}
            <strong className="text-emerald-400">0 credits</strong>
            {status.minutes_until_stale != null && status.minutes_until_stale > 0
              ? ` for ~${Math.round(status.minutes_until_stale)}m more`
              : ""}
            .
          </li>
        ) : needsLive ? (
          <li>
            Cached odds only cover{" "}
            <strong className="text-foreground">
              {nearLeagues.length ? nearLeagues.join(", ") : "a narrow slice"}
            </strong>
            . Tap <strong className="text-violet-300">Fetch live odds</strong> to scan MLB, WNBA, soccer,
            and more (~<strong className="text-foreground">{estimate}</strong> credits).
          </li>
        ) : (
          <li>
            Cache expired or empty — a live pull uses ~<strong className="text-amber-300">{estimate}</strong>{" "}
            credits ({scope}, max {status.max_sports_per_scan ?? 12} sports).
          </li>
        )}
        {remaining != null && (
          <li>
            Credits remaining across {status.key_count ?? status.keys?.length ?? 1} key
            {(status.key_count ?? 1) === 1 ? "" : "s"}:{" "}
            <strong className="text-foreground">{remaining.toLocaleString()}</strong>
            {status.monthly_capacity ? (
              <span className="text-muted"> / {status.monthly_capacity.toLocaleString()} monthly pool</span>
            ) : null}
          </li>
        )}
        <li>
          {rescoreFree ? (
            <>
              Prefer <strong className="text-foreground">Rescore</strong> while cache is warm. Use{" "}
              <strong className="text-foreground">Fetch live odds</strong> only when lines may have moved or
              leagues are missing.
            </>
          ) : needsLive ? (
            <>
              Use <strong className="text-foreground">Fetch live odds</strong> when the cache is missing
              in-season leagues.
            </>
          ) : (
            <>
              Use <strong className="text-foreground">Rescore</strong> when cache is fresh; use{" "}
              <strong className="text-foreground">Fetch live odds</strong> only when lines may have moved.
            </>
          )}
        </li>
      </ul>
      {status.error && <p className="mt-2 text-xs text-amber-300">{status.error}</p>}
    </div>
  );
}
