"use client";

import Link from "next/link";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { BudgetTag } from "@/components/ui/BudgetTag";
import { TradePlanPanel, type TradePlan } from "@/components/options/TradePlanPanel";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { optionSignalMetadata } from "@/lib/watchlist-api";
import { useState } from "react";

export interface OptionSignal {
  id: string;
  underlying: string;
  option_type: string;
  strike: number;
  expiration?: string;
  recommendation: string;
  explanation: string;
  confidence_score: number;
  risk_score: number;
  opportunity_score: number;
  premium: number;
  days_to_expiration: number;
  risk_warning: string;
  contract_cost?: number;
  is_budget?: boolean;
  context?: {
    top_headline?: string | null;
    has_catalyst?: boolean;
    profit_probability?: number;
    rsi?: number | null;
    relative_volume?: number;
  };
  scoring_snapshot?: {
    profit_probability?: number;
    trade_plan?: TradePlan;
    market_context?: Record<string, unknown>;
  };
}

function formatExpiration(expiration?: string) {
  if (!expiration) return null;
  return new Date(`${expiration}T12:00:00`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function OptionSignalCard({ row, rank }: { row: OptionSignal; rank: number }) {
  const [expanded, setExpanded] = useState(rank === 1);
  const tradePlan = row.scoring_snapshot?.trade_plan;
  const ctx = row.context ?? (row.scoring_snapshot?.market_context as OptionSignal["context"]);
  const winProb = row.scoring_snapshot?.profit_probability ?? ctx?.profit_probability;
  const expLabel = formatExpiration(row.expiration);
  const contractCost = row.contract_cost ?? row.premium * 100;
  const isBudget = row.is_budget ?? contractCost <= 100;
  const headline = ctx?.top_headline;

  return (
    <article
      className={`rounded-xl border bg-surface p-5 ${
        isBudget ? "border-emerald-500/50 ring-2 ring-emerald-500/20" : "border-border"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs uppercase tracking-wide text-muted">#{rank} · Options pick</p>
            {isBudget && <BudgetTag cost={contractCost} />}
            {ctx?.has_catalyst && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                📰 Catalyst
              </span>
            )}
          </div>
          <h2 className="mt-1 text-xl font-bold">
            {row.underlying} {row.option_type.toUpperCase()} ${Number(row.strike).toFixed(0)}
          </h2>
          <p className="mt-1 text-sm text-muted">
            Premium ${Number(row.premium).toFixed(2)} ·{" "}
            <span className={isBudget ? "font-semibold text-emerald-400" : "text-success"}>
              ${contractCost.toFixed(0)}/contract
            </span>{" "}
            · {row.days_to_expiration} days left
            {expLabel ? ` · Expires ${expLabel}` : ""}
          </p>
        </div>
        {winProb != null && (
          <div className="rounded-xl bg-success/15 px-4 py-2 text-center">
            <p className="text-xs text-success">Win probability</p>
            <p className="text-2xl font-bold text-success">{Number(winProb).toFixed(0)}%</p>
          </div>
        )}
      </div>

      {headline && (
        <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">
            Catalyst news
          </p>
          <p className="mt-1 text-sm leading-relaxed">{headline}</p>
        </div>
      )}

      <p className="mt-4 text-sm leading-relaxed">{row.recommendation}</p>

      {(ctx?.rsi != null || ctx?.relative_volume != null) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {ctx.rsi != null && (
            <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
              RSI {Number(ctx.rsi).toFixed(0)}
            </span>
          )}
          {ctx.relative_volume != null && (
            <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
              Vol {Number(ctx.relative_volume).toFixed(1)}x
            </span>
          )}
        </div>
      )}

      {tradePlan?.purchase_window && (
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="rounded-lg bg-accent/15 px-3 py-1.5 text-sm text-accent">
            Buy: {tradePlan.purchase_window.label}
          </span>
          <span className="rounded-lg bg-background px-3 py-1.5 text-sm text-muted">
            Breakeven ${tradePlan.breakeven_price.toFixed(2)}
          </span>
          <span className="rounded-lg bg-background px-3 py-1.5 text-sm text-muted">
            Need {tradePlan.move_needed_pct.toFixed(1)}% move
          </span>
        </div>
      )}

      <div className="mt-4 grid max-w-md grid-cols-3 gap-2">
        <ScoreBadge label="Confidence" value={Number(row.confidence_score)} variant="confidence" />
        <ScoreBadge label="Risk" value={Number(row.risk_score)} variant="risk" />
        <ScoreBadge label="Opportunity" value={Number(row.opportunity_score)} variant="opportunity" />
      </div>

      {tradePlan ? (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-sm font-medium text-accent hover:underline"
          >
            {expanded ? "Hide full trade plan" : "Show when to buy, ITM dates & strategies"}
          </button>
          {expanded && <TradePlanPanel plan={tradePlan} />}
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted">
          Run a new{" "}
          <Link href="/" className="text-accent underline">
            deep market scan
          </Link>{" "}
          to generate purchase dates and strategy comparisons.
        </p>
      )}

      <p className="mt-4 text-xs text-warning">{row.risk_warning}</p>

      <LogOutcomeButtons module="options" signalId={row.id} compact className="mt-4" />

      <div className="mt-3 flex flex-wrap gap-3">
        <AddToWatchlistButton
          symbol={row.id}
          itemType="option_signal"
          metadata={optionSignalMetadata(row)}
          label="Save to watchlist"
          variant="compact"
        />
        <Link href="/watchlist?tab=options" className="text-xs font-medium text-muted hover:text-accent">
          View watchlist →
        </Link>
      </div>
    </article>
  );
}
