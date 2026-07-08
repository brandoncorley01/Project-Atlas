"use client";

import { useCallback, useEffect, useState } from "react";
import {
  StatusGauge,
  finnhubGaugeValue,
  oddsCreditsGaugeValue,
} from "@/components/ui/StatusGauge";
import { apiPortLabel, API_START_HINT } from "@/lib/api-config";
import { apiRequestHeaders, getApiUrl } from "@/lib/api-url";
import { resolveOddsTotalCredits } from "@/lib/odds-credits";
import type { OddsApiStatus } from "@/lib/odds-status";

interface FinnhubStatus {
  configured?: boolean;
  connected?: boolean;
  error?: string | null;
  features?: string[];
}

interface OddsKeyStatus {
  index?: number;
  masked?: string;
  remaining?: number | null;
  used?: number | null;
  exhausted?: boolean;
  valid?: boolean;
  error?: string;
}

interface OddsStatus extends OddsApiStatus {
  features?: string[];
}

function FeatureChips({ items }: { items: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap justify-center gap-1.5">
      {items.slice(0, 4).map((f) => (
        <span
          key={f}
          className="rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-muted"
        >
          {f}
        </span>
      ))}
    </div>
  );
}

function OddsKeysList({
  keys,
  total,
  keyCount,
  activeKeyIndex,
}: {
  keys: OddsKeyStatus[];
  total: number | null;
  keyCount: number;
  activeKeyIndex?: number | null;
}) {
  if (!keys.length) return null;

  return (
    <div className="mt-4 w-full max-w-sm rounded-lg border border-violet-500/25 bg-violet-500/5 p-3 text-left">
      <p className="text-xs font-bold uppercase tracking-wider text-violet-300">
        {keyCount} API key{keyCount === 1 ? "" : "s"} configured
      </p>
      <ul className="mt-2 space-y-1.5">
        {keys.map((k, i) => (
          <li key={k.index ?? i} className="flex items-center justify-between gap-2 text-xs">
            <span className="font-mono text-muted">
              Key {k.index ?? i + 1}: {k.masked ?? "••••"}
              {activeKeyIndex === (k.index ?? i + 1) - 1 && (
                <span className="ml-1 font-sans font-semibold text-violet-300">· active</span>
              )}
            </span>
            <span
              className={
                k.exhausted
                  ? "font-semibold text-danger"
                  : k.remaining != null
                    ? "font-semibold text-success"
                    : "text-muted"
              }
            >
              {!k.valid ? "invalid" : k.exhausted ? "exhausted" : k.remaining != null ? `${k.remaining} cr` : "—"}
            </span>
          </li>
        ))}
      </ul>
      {total != null && (
        <p className="mt-2 border-t border-border/60 pt-2 text-xs font-semibold text-foreground">
          Combined pool: {total.toLocaleString()} credits
        </p>
      )}
    </div>
  );
}

export function DataProvidersPanel() {
  const [apiKey, setApiKey] = useState("");
  const [masked, setMasked] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [finnhub, setFinnhub] = useState<FinnhubStatus | null>(null);
  const [odds, setOdds] = useState<OddsStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const apiUrl = getApiUrl();
      const statusRes = await fetch(`${apiUrl}/providers/status`, {
        headers: apiRequestHeaders(),
        cache: "no-store",
      });

      if (!statusRes.ok) {
        setBackendError(`Backend unreachable — ${API_START_HINT}`);
        return;
      }
      setBackendError(null);
      const data = await statusRes.json();
      setFinnhub(data.finnhub ?? null);
      setOdds((data.odds_api ?? {}) as OddsStatus);
    } catch {
      setBackendError(`Could not reach API on port ${apiPortLabel()}`);
    }
    setStatusLoading(false);
  }, []);

  useEffect(() => {
    fetch("/api/finnhub")
      .then((r) => r.json())
      .then((d) => {
        setConfigured(Boolean(d.configured));
        setMasked(d.masked ?? null);
      })
      .catch(() => undefined);
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    void loadStatus();
    const onFocus = () => void loadStatus();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [configured, loadStatus]);

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

    setConfigured(true);
    setMasked(`${apiKey.slice(0, 4)}…${apiKey.slice(-4)}`);
    setApiKey("");
    setMessage("Key saved — restart the API to activate.");
    setShowKeyForm(false);
  }

  const fhValue = finnhubGaugeValue(
    Boolean(finnhub?.connected),
    Boolean(finnhub?.configured ?? configured),
    finnhub?.error,
  );

  const fhSubtitle = finnhub?.connected
    ? "RSI, trend & news active"
    : finnhub?.configured || configured
      ? "Key saved — restart API"
      : "Yahoo fallback only";

  const fhDetail =
    finnhub?.error && !finnhub.connected
      ? finnhub.error
      : masked
        ? `Key on file: ${masked}`
        : "Free key at finnhub.io/register";

  const keyCount = odds?.key_count ?? odds?.keys?.length ?? 0;
  const totalRemaining = resolveOddsTotalCredits(odds);

  const oddsValue = oddsCreditsGaugeValue(
    totalRemaining,
    Boolean(odds?.configured),
    Boolean(odds?.connected),
    Boolean(odds?.quota_exhausted),
    Math.max(1, keyCount),
  );

  const oddsCenterLabel =
    totalRemaining != null ? totalRemaining.toLocaleString() : odds?.configured ? "—" : undefined;

  const oddsSubtitle = !odds?.configured
    ? "Add ODDS_API_KEY to .env"
    : odds?.quota_exhausted && (totalRemaining ?? 0) <= 0
      ? "All keys exhausted"
      : keyCount > 1
        ? `${totalRemaining?.toLocaleString() ?? "?"} / ${(odds?.monthly_capacity ?? keyCount * 500).toLocaleString()} credits · ${keyCount} keys`
        : `${totalRemaining?.toLocaleString() ?? "?"} credits remaining`;

  const activeIdx = odds?.active_key_index;
  const oddsDetail = odds?.error
    ? odds.error
    : odds?.configured
      ? `Active key: #${(activeIdx ?? 0) + 1} · live scan ~${odds.estimated_live_scan_credits ?? "?"} credits${
          odds.cache_rescore_free
            ? ` · rescore free (${Math.round(odds.cache_age_minutes ?? 0)}m cache)`
            : odds.cache_fresh
              ? ` · cache fresh (${Math.round(odds.cache_age_minutes ?? 0)}m)`
              : ""
        }`
      : "Powers sports odds & +EV scans";

  const keysWithActive = odds?.keys ?? [];

  return (
    <div className="space-y-4">
      {backendError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {backendError}
        </p>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void loadStatus()}
          disabled={statusLoading}
          className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
        >
          {statusLoading ? "Refreshing…" : "Refresh status"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="atlas-card flex flex-col items-center p-5 sm:p-6">
          <p className="mb-1 self-start text-xs font-bold uppercase tracking-wider text-emerald-400">
            Stocks & news
          </p>
          <StatusGauge
            value={fhValue}
            title="Finnhub"
            subtitle={fhSubtitle}
            detail={fhDetail}
          />
          <FeatureChips
            items={finnhub?.features ?? ["stock quotes", "RSI / trend", "news catalysts"]}
          />
        </div>

        <div className="atlas-card flex flex-col items-center p-5 sm:p-6">
          <p className="mb-1 self-start text-xs font-bold uppercase tracking-wider text-violet-400">
            Sports odds
          </p>
          <StatusGauge
            value={oddsValue}
            title="The Odds API"
            subtitle={oddsSubtitle}
            detail={oddsDetail}
            centerLabel={oddsCenterLabel}
          />
          <OddsKeysList
            keys={keysWithActive}
            total={totalRemaining}
            keyCount={keyCount}
            activeKeyIndex={activeIdx}
          />
          <FeatureChips
            items={odds?.features ?? ["live odds", "+EV scan", "multi-book", "parlay legs"]}
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
              Optional free key from{" "}
              <a
                href="https://finnhub.io/register"
                target="_blank"
                rel="noreferrer"
                className="text-accent underline"
              >
                finnhub.io/register
              </a>
              . Odds API keys: comma-separated in{" "}
              <code className="text-foreground">apps/api/.env</code> (you have {keyCount || 3} configured
              after restart).
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
                {loading ? "Saving…" : configured ? "Update key" : "Save key"}
              </button>
            </form>
            {message && <p className="mt-2 text-xs text-muted">{message}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
