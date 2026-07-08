"use client";

import { useCallback, useEffect, useState } from "react";
import {
  StatusGauge,
  finnhubGaugeValue,
  oddsCreditsGaugeValue,
} from "@/components/ui/StatusGauge";
import { API_START_HINT } from "@/lib/api-config";
import { usesBffProxy } from "@/lib/api-url";
import { resolveOddsTotalCredits } from "@/lib/odds-credits";
import { fetchProvidersStatus, type OddsApiStatus } from "@/lib/odds-status";

interface FinnhubStatus {
  configured?: boolean;
  connected?: boolean;
  error?: string | null;
}

interface OddsStatus extends OddsApiStatus {
  features?: string[];
}

function formatUpdatedAt(date: Date | null) {
  if (!date) return null;
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function buildOddsDescription(odds: OddsStatus | null, remaining: number | null): string {
  if (!odds?.configured) {
    return "Add comma-separated keys to ODDS_API_KEY in apps/api/.env (local) or Render (production). Each free account includes 500 credits per month with automatic failover.";
  }
  if (odds.error) return odds.error;

  const parts: string[] = [];
  const keyCount = odds.key_count ?? odds.keys?.length ?? 1;
  const capacity = odds.monthly_capacity ?? keyCount * 500;

  parts.push(
    `${keyCount} API key${keyCount === 1 ? "" : "s"} pooled · ${capacity.toLocaleString()} credits/month capacity.`,
  );

  if (remaining != null) {
    const used = Math.max(0, capacity - remaining);
    parts.push(`~${used.toLocaleString()} used this cycle · ${remaining.toLocaleString()} left.`);
  }

  const active = (odds.active_key_index ?? 0) + 1;
  parts.push(`Failover active on key #${active}.`);

  if (odds.cache_rescore_free) {
    parts.push(
      `Cached odds (${Math.round(odds.cache_age_minutes ?? 0)}m old) — rescore costs 0 credits for ~${Math.round(odds.minutes_until_stale ?? 0)}m more.`,
    );
  } else {
    parts.push(`Live scan uses ~${odds.estimated_live_scan_credits ?? "?"} credits; rescore when cache is warm.`);
  }

  return parts.join(" ");
}

export function DataProvidersPanel() {
  const [apiKey, setApiKey] = useState("");
  const [masked, setMasked] = useState<string | null>(null);
  const [finnhubConfigured, setFinnhubConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [finnhub, setFinnhub] = useState<FinnhubStatus | null>(null);
  const [odds, setOdds] = useState<OddsStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadStatus = useCallback(async (refresh = false) => {
    setStatusLoading(true);
    try {
      let token: string | undefined;
      if (!usesBffProxy()) {
        const { createClient } = await import("@/lib/supabase/client");
        const { data } = await createClient().auth.getSession();
        token = data.session?.access_token ?? undefined;
      }

      const data = await fetchProvidersStatus(token, refresh);
      if (!data) {
        setBackendError(`Backend unreachable — ${API_START_HINT}`);
        setStatusLoading(false);
        return;
      }

      setBackendError(null);
      setFinnhub((data.finnhub ?? null) as FinnhubStatus | null);
      setOdds((data.odds_api ?? null) as OddsStatus | null);
      setLastUpdated(new Date());
    } catch {
      setBackendError(`Could not reach the API — ${API_START_HINT}`);
    }
    setStatusLoading(false);
  }, []);

  useEffect(() => {
    fetch("/api/finnhub")
      .then((r) => r.json())
      .then((d) => {
        setFinnhubConfigured(Boolean(d.configured));
        setMasked(d.masked ?? null);
      })
      .catch(() => undefined);
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    const onRefresh = () => void loadStatus();
    window.addEventListener("atlas:dashboard-refresh", onRefresh);
    window.addEventListener("focus", onRefresh);
    const interval = window.setInterval(onRefresh, 90_000);
    return () => {
      window.removeEventListener("atlas:dashboard-refresh", onRefresh);
      window.removeEventListener("focus", onRefresh);
      window.clearInterval(interval);
    };
  }, [loadStatus]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);

    const res = await fetch("/api/finnhub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    });
    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      setMessage(data.error ?? "Failed to save");
      return;
    }

    setFinnhubConfigured(true);
    setMasked(`${apiKey.slice(0, 4)}…${apiKey.slice(-4)}`);
    setApiKey("");
    setMessage("Key saved — restart the API to activate.");
    setShowKeyForm(false);
    void loadStatus();
  }

  const fhValue = finnhubGaugeValue(
    Boolean(finnhub?.connected),
    Boolean(finnhub?.configured ?? finnhubConfigured),
    finnhub?.error,
  );

  const fhSubtitle = finnhub?.connected
    ? "Connected · RSI, trend & news"
    : finnhub?.configured || finnhubConfigured
      ? "Key saved — restart API"
      : "Not configured";

  const fhDetail =
    finnhub?.error && !finnhub.connected
      ? finnhub.error
      : masked
        ? `Finnhub key on file (${masked}). Powers stock RSI, relative volume, and news catalysts.`
        : "Optional free key from finnhub.io/register. Without it, Atlas uses Yahoo quotes only.";

  const keyCount = Math.max(1, odds?.key_count ?? odds?.keys?.length ?? 0);
  const totalRemaining = resolveOddsTotalCredits(odds);
  const monthlyCapacity = odds?.monthly_capacity ?? keyCount * 500;

  const oddsValue = oddsCreditsGaugeValue(
    totalRemaining,
    Boolean(odds?.configured),
    Boolean(odds?.connected),
    Boolean(odds?.quota_exhausted),
    keyCount,
    monthlyCapacity,
  );

  const oddsCenterLabel =
    totalRemaining != null
      ? totalRemaining.toLocaleString()
      : odds?.configured
        ? "—"
        : undefined;

  const oddsSubtitle = !odds?.configured
    ? "Not configured"
    : odds.quota_exhausted && (totalRemaining ?? 0) <= 0
      ? "All keys exhausted"
      : `${totalRemaining?.toLocaleString() ?? "—"} / ${monthlyCapacity.toLocaleString()} credits`;

  const oddsDetail = buildOddsDescription(odds, totalRemaining);
  const updatedLabel = formatUpdatedAt(lastUpdated);

  return (
    <div className="space-y-4">
      {backendError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {backendError}
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted">
          {updatedLabel ? `Last updated ${updatedLabel}` : "Checking provider status…"}
        </p>
        <button
          type="button"
          onClick={() => void loadStatus(true)}
          disabled={statusLoading}
          className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
        >
          {statusLoading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="atlas-card flex flex-col items-center p-5 sm:p-6">
          <StatusGauge
            value={fhValue}
            title="Finnhub"
            subtitle={fhSubtitle}
            detail={fhDetail}
          />
        </div>

        <div className="atlas-card flex flex-col items-center p-5 sm:p-6">
          <StatusGauge
            value={oddsValue}
            title="The Odds API"
            subtitle={oddsSubtitle}
            detail={oddsDetail}
            centerLabel={oddsCenterLabel}
          />
        </div>
      </div>

      <div className="atlas-card p-4">
        <button
          type="button"
          onClick={() => setShowKeyForm((v) => !v)}
          className="flex w-full items-center justify-between text-left text-sm font-semibold text-foreground"
        >
          <span>Manage Finnhub API key</span>
          <span className="text-xs text-muted">{showKeyForm ? "Hide ▲" : "Show ▼"}</span>
        </button>

        {showKeyForm && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="text-xs leading-relaxed text-muted">
              Odds API keys are managed in <code className="text-foreground">apps/api/.env</code> or Render — not here.
            </p>
            <form onSubmit={handleSave} className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste Finnhub API key"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={loading || !apiKey}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {loading ? "Saving…" : finnhubConfigured ? "Update key" : "Save key"}
              </button>
            </form>
            {message && <p className="mt-2 text-xs text-muted">{message}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
