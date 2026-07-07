"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { resolveOddsTotalCredits } from "@/lib/odds-credits";
import { mergeOddsKeyProbe } from "@/lib/merge-odds-status";

export interface OddsApiStatus {
  configured: boolean;
  connected: boolean;
  quota_exhausted?: boolean;
  total_remaining?: number | null;
  key_count?: number;
  keys?: Array<{ index?: number; masked?: string; remaining?: number | null; exhausted?: boolean; valid?: boolean }>;
  requests_remaining?: string | number | null;
  cache_has_data?: boolean;
  cache_age_minutes?: number | null;
  cache_fresh?: boolean;
  cache_needs_live_refresh?: boolean;
  near_term_leagues?: string[];
  near_term_event_count?: number;
  cache_ttl_minutes?: number;
  minutes_until_stale?: number;
  scan_scope?: string;
  max_sports_per_scan?: number;
  estimated_live_scan_credits?: number;
  error?: string | null;
}

export function useOddsApiStatus() {
  const [status, setStatus] = useState<OddsApiStatus | null>(null);

  const refresh = useCallback(async () => {
    const apiUrl = getApiUrl();
    let token: string | undefined;
    if (!usesBffProxy()) {
      const { createClient } = await import("@/lib/supabase/client");
      const { data } = await createClient().auth.getSession();
      token = data.session?.access_token ?? undefined;
    }
    try {
      const [statusRes, keysRes] = await Promise.all([
        fetch(`${apiUrl}/providers/status`, { headers: apiRequestHeaders(token) }),
        fetch("/api/odds-keys"),
      ]);
      if (statusRes.ok) {
        const data = await statusRes.json();
        let oddsData = data.odds_api ?? null;
        if (keysRes.ok) {
          const keyProbe = await keysRes.json();
          oddsData = mergeOddsKeyProbe(oddsData, keyProbe);
        }
        setStatus(oddsData);
      }
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { status, refresh };
}

export function OddsQuotaBanner({ status }: { status: OddsApiStatus | null }) {
  if (!status?.configured) return null;

  const fresh = status.cache_fresh;
  const needsLive = status.cache_needs_live_refresh;
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
          : needsLive
            ? "border-violet-500/40 bg-violet-500/10"
            : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <p className="font-medium text-foreground">Odds API quota conservation</p>
      <ul className="mt-2 space-y-1 text-xs text-muted">
        {needsLive ? (
          <li>
            Cached odds only cover{" "}
            <strong className="text-foreground">
              {nearLeagues.length ? nearLeagues.join(", ") : "a narrow slice"}
            </strong>
            . Tap <strong className="text-violet-300">Fetch live odds</strong> to scan MLB, WNBA, soccer,
            and more (~<strong className="text-foreground">{estimate}</strong> credits).{" "}
            <strong className="text-foreground">Rescore</strong> reuses this narrow cache at 0 credits.
          </li>
        ) : fresh && age != null ? (
          <li>
            Cached odds are <strong className="text-foreground">{Math.round(age)}m old</strong> — rescan
            uses <strong className="text-emerald-400">0 credits</strong> for{" "}
            {status.minutes_until_stale != null
              ? `~${Math.round(status.minutes_until_stale)}m more`
              : "the TTL window"}
            .
          </li>
        ) : (
          <li>
            Cache expired or empty — a live pull uses ~<strong className="text-amber-300">{estimate}</strong>{" "}
            credits ({scope}, max {status.max_sports_per_scan ?? 12} sports).
          </li>
        )}
        {remaining != null && (
          <li>
            Estimated credits remaining across keys:{" "}
            <strong className="text-foreground">{remaining}</strong>
          </li>
        )}
        <li>
          {needsLive ? (
            <>
              Use <strong className="text-foreground">Fetch live odds</strong> when the cache is missing
              in-season leagues; use <strong className="text-foreground">Rescore</strong> only to
              re-analyze the current cache.
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
