"use client";

import Link from "next/link";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { StockChart, type ChartBar } from "@/components/charts/StockChart";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { stockSignalMetadata } from "@/lib/watchlist-api";
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
}

function timeframeLabel(timeframe?: string) {
  if (timeframe === "swing_short") return "2–7 day swing";
  if (timeframe === "swing_medium") return "1–2 week swing";
  return "Swing trade";
}

export function StockSignalCard({
  row,
  rank,
  showChart = false,
}: {
  row: StockSignal;
  rank: number;
  showChart?: boolean;
}) {
  const [expanded, setExpanded] = useState(rank === 1 || showChart);
  const tech = row.technicals ?? {};
  const bullish = tech.trend === "bullish";
  const entry = row.entry_range ?? {};
  const headline = row.context?.top_headline;

  return (
    <article className="rounded-xl border border-border bg-surface p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs uppercase tracking-wide text-muted">#{rank} · Stock swing</p>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                bullish ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
              }`}
            >
              {bullish ? "Bullish" : "Bearish"}
            </span>
            {row.context?.has_catalyst && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                📰 Catalyst
              </span>
            )}
          </div>
          <h2 className="mt-1 text-xl font-bold">
            {row.ticker}{" "}
            <span className="text-lg font-semibold text-muted">
              ${Number(row.current_price).toFixed(2)}
            </span>
          </h2>
          <p className="mt-1 text-sm text-muted">
            {timeframeLabel(row.timeframe)} · Hold {row.expected_hold_time ?? "—"}
          </p>
        </div>
        <div className="grid w-full shrink-0 grid-cols-3 gap-2 sm:w-auto sm:min-w-[240px]">
          <ScoreBadge label="Conf." value={row.confidence_score} variant="confidence" />
          <ScoreBadge label="Risk" value={row.risk_score} variant="risk" />
          <ScoreBadge label="Opp." value={row.opportunity_score} variant="opportunity" />
        </div>
      </div>

      <p className="mt-3 font-medium">{row.recommendation}</p>

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
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-background/50 p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Entry zone</p>
          <p className="mt-1 text-sm font-semibold">
            ${Number(entry.low ?? 0).toFixed(2)} – ${Number(entry.high ?? 0).toFixed(2)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-background/50 p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Stop loss</p>
          <p className="mt-1 text-sm font-semibold text-danger">
            ${Number(row.stop_loss ?? 0).toFixed(2)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-background/50 p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Targets</p>
          <p className="mt-1 text-sm font-semibold text-success">
            {(row.profit_targets ?? []).map((t) => `$${Number(t).toFixed(2)}`).join(" · ") || "—"}
          </p>
        </div>
      </div>

      {headline && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">Catalyst</p>
          <p className="mt-1 text-sm">{headline}</p>
        </div>
      )}

      {!showChart && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-sm font-medium text-accent hover:underline"
          >
            {expanded ? "Hide details" : "Show trade plan & chart"}
          </button>
          <Link href={`/stocks/${row.id}`} className="text-sm font-medium text-accent hover:underline">
            Full detail page →
          </Link>
          <AddToWatchlistButton
            symbol={row.id}
            itemType="stock_signal"
            metadata={stockSignalMetadata(row)}
            label="Save to watchlist"
            variant="compact"
          />
          <AddToWatchlistButton
            symbol={row.ticker}
            itemType="ticker"
            metadata={{ label: `${row.ticker} ticker` }}
            label={`Track ${row.ticker}`}
            variant="compact"
          />
        </div>
      )}

      {expanded && (
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
          {(row.chart_bars?.length ?? 0) > 0 && (
            <StockChart
              bars={row.chart_bars ?? []}
              entryLow={entry.low}
              entryHigh={entry.high}
              stopLoss={row.stop_loss}
              profitTargets={row.profit_targets}
            />
          )}
          {row.risk_warning && (
            <p className="text-xs text-muted">{row.risk_warning}</p>
          )}
          <LogOutcomeButtons module="stock" signalId={row.id} className="pt-2 border-t border-border" />
        </div>
      )}
    </article>
  );
}
