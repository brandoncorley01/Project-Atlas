"use client";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { StockChart, type ChartBar } from "@/components/charts/StockChart";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { PickPerformanceBadge } from "@/components/performance/PickPerformanceBadge";
import { AtlasExplainButton } from "@/components/ai/AtlasExplainButton";
import { stockSignalMetadata } from "@/lib/watchlist-api";
import { formatRiskReward, midpoint, riskRewardRatio } from "@/lib/trade-metrics";
import Link from "next/link";
import { useState } from "react";

export interface StockSignal {
  id: string;
  ticker: string;
  current_price: number;
  recommendation: string;
  explanation: string;
  confidence_score: number;
  risk_score: number;
  opportunity_score: number;
  entry_range?: { low?: number; high?: number };
  stop_loss?: number;
  profit_targets?: number[];
  expected_hold_time?: string;
  timeframe?: string;
  technicals?: {
    rsi?: number | null;
    relative_volume?: number;
    macd_histogram?: number | null;
    sma20?: number | null;
    trend?: string;
    vs_sma20_pct?: number | null;
  };
  bull_case?: string | null;
  bear_case?: string | null;
  invalidation?: string | null;
  suggested_action?: string | null;
  risk_warning?: string;
  context?: {
    has_catalyst?: boolean;
    top_headline?: string | null;
    trend_bullish?: boolean;
  };
  chart_bars?: ChartBar[];
  scoring_snapshot?: {
    weak_setup?: boolean;
  };
}

function timeframeLabel(timeframe?: string) {
  if (timeframe === "swing_short") return "2–7 day swing";
  if (timeframe === "swing_medium") return "1–2 week swing";
  return "Swing trade";
}

function isLookupId(id: string) {
  return id.startsWith("lookup-");
}

export function StockSignalCard({
  row,
  rank,
  showChart = false,
  lookupMode = false,
  embedded = false,
}: {
  row: StockSignal;
  rank: number;
  showChart?: boolean;
  lookupMode?: boolean;
  /** When true (watchlist/performance), stay in place — no origin-page link. */
  embedded?: boolean;
}) {
  const [expanded, setExpanded] = useState(rank === 1 || showChart || lookupMode);
  const tech = row.technicals ?? {};
  const bullish = tech.trend === "bullish";
  const entry = row.entry_range ?? {};
  const headline = row.context?.top_headline;
  const weakSetup = row.scoring_snapshot?.weak_setup;
  const entryMid = midpoint(entry.low, entry.high) ?? row.current_price;
  const target1 = row.profit_targets?.[0] ?? null;
  const target2 = row.profit_targets?.[1] ?? null;
  const rr1 = formatRiskReward(riskRewardRatio(entryMid, row.stop_loss ?? null, target1));
  const chartVisible = lookupMode || showChart || expanded;
  const canSaveOutcome = !isLookupId(row.id);

  return (
    <article className="w-full max-w-full overflow-hidden rounded-xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs uppercase tracking-wide text-muted">
          #{rank} · {lookupMode ? "Ticker analysis" : "Stock swing"}
        </p>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            bullish ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
          }`}
        >
          {bullish ? "Bullish" : "Bearish"}
        </span>
        {weakSetup && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
            Watchlist only
          </span>
        )}
        {row.context?.has_catalyst && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
            📰 Catalyst
          </span>
        )}
        {canSaveOutcome && <PickPerformanceBadge module="stock" signalId={row.id} />}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,260px)] lg:items-start">
        <div className="min-w-0">
          <h2 className="text-xl font-bold leading-tight text-balance sm:text-2xl">
            {row.ticker}{" "}
            <span className="text-lg font-semibold text-muted">
              ${Number(row.current_price).toFixed(2)}
            </span>
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {timeframeLabel(row.timeframe)} · Hold {row.expected_hold_time ?? "—"}
          </p>
        </div>
        <div className="grid w-full grid-cols-3 gap-2">
          <ScoreBadge label="Confidence" shortLabel="Conf." value={row.confidence_score} variant="confidence" />
          <ScoreBadge label="Risk" value={row.risk_score} variant="risk" />
          <ScoreBadge label="Opportunity" shortLabel="Opp." value={row.opportunity_score} variant="opportunity" />
        </div>
      </div>

      <p className="mt-3 text-sm font-medium leading-relaxed [overflow-wrap:anywhere] sm:text-base">
        {row.recommendation}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {tech.rsi != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            RSI {Number(tech.rsi).toFixed(0)}
          </span>
        )}
        {tech.relative_volume != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            Vol {Number(tech.relative_volume).toFixed(1)}x
          </span>
        )}
        {tech.macd_histogram != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            MACD {Number(tech.macd_histogram) >= 0 ? "+" : ""}
            {Number(tech.macd_histogram).toFixed(2)}
          </span>
        )}
        {tech.sma20 != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            SMA20 ${Number(tech.sma20).toFixed(2)}
          </span>
        )}
        {tech.vs_sma20_pct != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            vs SMA20 {Number(tech.vs_sma20_pct) >= 0 ? "+" : ""}
            {Number(tech.vs_sma20_pct).toFixed(1)}%
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-accent/30 bg-accent/10 p-3">
          <p className="text-xs uppercase tracking-wide text-accent">Entry zone</p>
          <p className="mt-1 text-sm font-semibold">
            ${Number(entry.low ?? 0).toFixed(2)} – ${Number(entry.high ?? 0).toFixed(2)}
          </p>
          <p className="mt-1 text-xs text-muted">Where to open the position</p>
        </div>
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-3">
          <p className="text-xs uppercase tracking-wide text-danger">Stop loss</p>
          <p className="mt-1 text-sm font-semibold text-danger">
            ${Number(row.stop_loss ?? 0).toFixed(2)}
          </p>
          <p className="mt-1 text-xs text-muted">Exit if thesis breaks</p>
        </div>
        <div className="rounded-lg border border-success/30 bg-success/10 p-3">
          <p className="text-xs uppercase tracking-wide text-success">Take profit</p>
          <p className="mt-1 text-sm font-semibold text-success">
            {target1 != null ? `$${Number(target1).toFixed(2)}` : "—"}
            {target2 != null ? ` · $${Number(target2).toFixed(2)}` : ""}
          </p>
          <p className="mt-1 text-xs text-muted">T1 {target2 != null ? "· T2 scale-out" : "first target"}</p>
        </div>
        <div className="rounded-lg border border-border bg-background/50 p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Risk / reward</p>
          <p className="mt-1 text-sm font-semibold">{rr1}</p>
          <p className="mt-1 text-xs text-muted">To first target vs stop</p>
        </div>
      </div>

      {headline && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">Catalyst</p>
          <p className="mt-1 text-sm">{headline}</p>
        </div>
      )}

      {(row.chart_bars?.length ?? 0) > 0 && chartVisible && (
        <div className="mt-4">
          <StockChart
            bars={row.chart_bars ?? []}
            entryLow={entry.low}
            entryHigh={entry.high}
            stopLoss={row.stop_loss}
            profitTargets={row.profit_targets}
          />
        </div>
      )}

      {!lookupMode && !showChart && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-sm font-medium text-accent hover:underline"
          >
            {expanded ? "Hide trade plan" : "Show trade plan & chart"}
          </button>
          {!embedded && !isLookupId(row.id) && (
            <Link href={`/stocks/${row.id}`} className="text-sm font-medium text-accent hover:underline">
              Full detail page →
            </Link>
          )}
          {!embedded && (
            <AddToWatchlistButton
              symbol={canSaveOutcome ? row.id : row.ticker}
              itemType={canSaveOutcome ? "stock_signal" : "ticker"}
              metadata={stockSignalMetadata(row)}
              label="Save to watchlist"
              variant="compact"
            />
          )}
        </div>
      )}

      {(expanded || lookupMode) && (
        <div className="mt-4 space-y-4 border-t border-border pt-4">
          <p className="text-sm text-muted">{row.explanation}</p>
          {row.suggested_action && (
            <p className="text-sm">
              <span className="font-medium">Action:</span> {row.suggested_action}
            </p>
          )}
          {row.invalidation && (
            <p className="text-sm text-danger">
              <span className="font-medium">Invalidation:</span> {row.invalidation}
            </p>
          )}
          {row.bull_case && (
            <p className="text-sm">
              <span className="font-medium text-success">Bull case:</span> {row.bull_case}
            </p>
          )}
          {row.bear_case && (
            <p className="text-sm">
              <span className="font-medium text-danger">Bear case:</span> {row.bear_case}
            </p>
          )}
          {row.risk_warning && (
            <p className="text-xs text-muted">{row.risk_warning}</p>
          )}
          {canSaveOutcome && (
            <>
              <AtlasExplainButton module="stock" signalId={row.id} className="pt-2" />
              <LogOutcomeButtons module="stock" signalId={row.id} className="pt-2 border-t border-border" />
            </>
          )}
          {lookupMode && (
            <div className="flex flex-wrap gap-3 pt-2">
              <AddToWatchlistButton
                symbol={row.ticker}
                itemType="ticker"
                metadata={{ label: `${row.ticker} ticker` }}
                label={`Track ${row.ticker}`}
                variant="compact"
              />
            </div>
          )}
        </div>
      )}
    </article>
  );
}
