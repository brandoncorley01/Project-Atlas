"use client";

import { useEffect, useState } from "react";
import { OptionSignalCard, type OptionSignal } from "@/components/options/OptionSignalCard";
import { ParlayCard, type Parlay } from "@/components/parlays/ParlayCard";
import { SportsSignalCard, type SportsSignal } from "@/components/sports/SportsSignalCard";
import { StockSignalCard, type StockSignal } from "@/components/stocks/StockSignalCard";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import {
  effectiveItemType,
  normalizeWatchlistSymbol,
  type WatchlistItem,
} from "@/lib/watchlist-types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

function resolveDetailTarget(item: WatchlistItem): {
  kind: "sports" | "stock" | "options" | "parlay" | "ticker" | null;
  id: string | null;
} {
  const kind = effectiveItemType(item);
  const meta = item.metadata ?? {};

  if (kind === "ticker") {
    return { kind: "ticker", id: item.symbol };
  }

  if (kind === "parlay") {
    if (typeof meta.parlay_id === "string" && meta.parlay_id.trim()) {
      return { kind: "parlay", id: normalizeWatchlistSymbol(meta.parlay_id) };
    }
    if (UUID_RE.test(item.symbol)) {
      return { kind: "parlay", id: normalizeWatchlistSymbol(item.symbol) };
    }
    return { kind: "parlay", id: null };
  }

  const signalId =
    typeof meta.signal_id === "string" && meta.signal_id.trim()
      ? normalizeWatchlistSymbol(meta.signal_id)
      : UUID_RE.test(item.symbol)
        ? normalizeWatchlistSymbol(item.symbol)
        : null;

  if (kind === "sport_bet") return { kind: "sports", id: signalId };
  if (kind === "stock_signal") return { kind: "stock", id: signalId };
  if (kind === "option_signal") return { kind: "options", id: signalId };
  return { kind: null, id: null };
}

function TickerDetail({ item }: { item: WatchlistItem }) {
  const meta = item.metadata ?? {};
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-lg font-semibold">{item.symbol}</p>
      <p className="mt-1 text-sm text-muted">
        Saved ticker · included in stock and options scans.
      </p>
      {typeof meta.label === "string" && meta.label !== item.symbol && (
        <p className="mt-2 text-sm text-muted">{meta.label}</p>
      )}
      <p className="mt-3 text-xs text-muted">
        Run a Stocks or Options scan to generate a full play card for this ticker.
      </p>
    </div>
  );
}

function MetadataFallback({ item }: { item: WatchlistItem }) {
  const meta = item.metadata ?? {};
  const kind = effectiveItemType(item);
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-sm font-semibold text-foreground">
        {typeof meta.label === "string" ? meta.label : item.symbol}
      </p>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        {kind === "sport_bet" && (
          <>
            {meta.event_name != null && (
              <div>
                <dt className="text-xs text-muted">Event</dt>
                <dd>{String(meta.event_name)}</dd>
              </div>
            )}
            {meta.bet_type != null && (
              <div>
                <dt className="text-xs text-muted">Bet type</dt>
                <dd className="capitalize">{String(meta.bet_type)}</dd>
              </div>
            )}
            {meta.selection != null && (
              <div>
                <dt className="text-xs text-muted">Selection</dt>
                <dd>{String(meta.selection)}</dd>
              </div>
            )}
            {meta.odds_american != null && (
              <div>
                <dt className="text-xs text-muted">Odds</dt>
                <dd>
                  {Number(meta.odds_american) > 0 ? "+" : ""}
                  {String(meta.odds_american)}
                </dd>
              </div>
            )}
          </>
        )}
        {(kind === "stock_signal" || kind === "option_signal") && (
          <>
            {meta.recommendation != null && (
              <div>
                <dt className="text-xs text-muted">Recommendation</dt>
                <dd>{String(meta.recommendation)}</dd>
              </div>
            )}
            {meta.opportunity_score != null && (
              <div>
                <dt className="text-xs text-muted">Opportunity</dt>
                <dd>{Number(meta.opportunity_score).toFixed(0)}</dd>
              </div>
            )}
          </>
        )}
        {kind === "parlay" && Array.isArray(meta.legs) && (
          <div className="sm:col-span-2">
            <dt className="text-xs text-muted">Legs</dt>
            <dd>
              <ul className="mt-1 space-y-1">
                {(meta.legs as Array<{ selection?: string; odds_american?: number }>).map(
                  (leg, i) => (
                    <li key={i}>
                      {leg.selection}
                      {leg.odds_american != null && (
                        <span className="ml-1 text-muted">
                          ({leg.odds_american > 0 ? "+" : ""}
                          {leg.odds_american})
                        </span>
                      )}
                    </li>
                  ),
                )}
              </ul>
            </dd>
          </div>
        )}
      </dl>
      <p className="mt-3 text-xs text-muted">
        Full live card unavailable — showing the details saved with this watchlist pick.
      </p>
    </div>
  );
}

export function WatchlistPickDetail({
  item,
  onClose,
}: {
  item: WatchlistItem;
  onClose: () => void;
}) {
  const target = resolveDetailTarget(item);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sports, setSports] = useState<SportsSignal | null>(null);
  const [stock, setStock] = useState<StockSignal | null>(null);
  const [option, setOption] = useState<OptionSignal | null>(null);
  const [parlay, setParlay] = useState<Parlay | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setSports(null);
      setStock(null);
      setOption(null);
      setParlay(null);

      if (target.kind === "ticker") {
        if (!cancelled) setLoading(false);
        return;
      }

      if (!target.kind || !target.id) {
        if (!cancelled) {
          setError(null);
          setLoading(false);
        }
        return;
      }

      try {
        const token = await getToken();
        const apiUrl = getApiUrl();
        const path =
          target.kind === "sports"
            ? `/signals/sports/${target.id}`
            : target.kind === "stock"
              ? `/signals/stocks/${target.id}`
              : target.kind === "options"
                ? `/signals/options/${target.id}`
                : `/parlays/${target.id}?for_edit=true`;

        const res = await fetch(`${apiUrl}${path}`, {
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
          cache: "no-store",
          signal: AbortSignal.timeout(45_000),
        });

        if (!res.ok) {
          throw new Error(
            res.status === 404
              ? "This pick is no longer on the live board — showing saved details below."
              : "Could not load pick details",
          );
        }

        const data = await res.json();
        if (cancelled) return;

        if (target.kind === "sports") setSports(data as SportsSignal);
        else if (target.kind === "stock") setStock(data as StockSignal);
        else if (target.kind === "options") setOption(data as OptionSignal);
        else setParlay(data as Parlay);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load pick details");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [item.id, target.kind, target.id]);

  const hasLiveCard = Boolean(sports || stock || option || parlay);

  return (
    <div className="mt-3 space-y-3 border-t border-border/60 pt-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          Pick details
        </p>
        <button
          type="button"
          onClick={onClose}
          className="text-xs font-medium text-accent hover:underline"
        >
          Hide details
        </button>
      </div>

      {loading && (
        <p className="text-sm text-muted">Loading pick from your saved watchlist…</p>
      )}

      {!loading && target.kind === "ticker" && <TickerDetail item={item} />}

      {!loading && sports && (
        <SportsSignalCard row={sports} rank={1} hideSelection embedded />
      )}
      {!loading && stock && <StockSignalCard row={stock} rank={1} showChart embedded />}
      {!loading && option && <OptionSignalCard row={option} rank={1} embedded />}
      {!loading && parlay && <ParlayCard row={parlay} rank={1} embedded />}

      {!loading && !hasLiveCard && target.kind !== "ticker" && (
        <>
          {error && <p className="text-xs text-amber-200/90">{error}</p>}
          <MetadataFallback item={item} />
        </>
      )}
    </div>
  );
}

/** Whether this watchlist row can open an in-place detail panel. */
export function watchlistItemCanOpenDetails(item: WatchlistItem): boolean {
  const target = resolveDetailTarget(item);
  if (target.kind === "ticker") return true;
  if (target.kind && target.id) return true;
  // Parlay / picks that only have metadata still open a saved snapshot.
  const kind = effectiveItemType(item);
  return kind === "sport_bet" || kind === "stock_signal" || kind === "option_signal" || kind === "parlay";
}

/** Build a synthetic watchlist item so Performance can reuse inline details. */
export function performanceEntryAsWatchlistItem(row: {
  id: string;
  module: string;
  signal_id: string;
  signal_label?: string | null;
  leg_outcomes?: Array<Record<string, unknown>> | null;
}): WatchlistItem {
  const module = row.module;
  const kind =
    module === "sports"
      ? "sport_bet"
      : module === "stock"
        ? "stock_signal"
        : module === "options"
          ? "option_signal"
          : module === "parlay"
            ? "parlay"
            : "ticker";

  return {
    id: row.id,
    item_type: kind,
    symbol: row.signal_id,
    metadata: {
      watchlist_kind: kind,
      signal_id: row.signal_id,
      ...(kind === "parlay" ? { parlay_id: row.signal_id } : {}),
      label: row.signal_label ?? row.signal_id,
      ...(Array.isArray(row.leg_outcomes) ? { legs: row.leg_outcomes } : {}),
    },
  };
}
