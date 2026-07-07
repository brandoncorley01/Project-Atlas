"use client";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { BudgetTag } from "@/components/ui/BudgetTag";
import { EmptyState } from "@/components/ui/EmptyState";
import { BookOddsStrip, type BookOddsLine } from "@/components/sports/BookOddsStrip";
import Link from "next/link";

export interface SignalContext {
  rsi?: number | null;
  relative_volume?: number;
  has_catalyst?: boolean;
  news_count?: number;
  top_headline?: string | null;
  trend_bullish?: boolean;
  profit_probability?: number;
  delta?: number;
  discovery_sources?: string[];
  expected_value?: number;
  edge_pct?: number;
  sharp_indicator?: string | null;
  bet_type?: string;
  book_odds?: BookOddsLine[];
  preferred_book?: string;
}

export interface TradePlanSummary {
  purchase_window?: { label: string; friendly?: string };
  expiration_label?: string;
  breakeven_price?: number;
  move_needed_pct?: number;
}

export interface SignalSummary {
  id: string;
  module: string;
  title: string;
  recommendation: string;
  explanation?: string;
  context?: SignalContext;
  trade_plan?: TradePlanSummary;
  expiration?: string;
  contract_cost?: number;
  is_budget?: boolean;
  premium?: number;
  scores: {
    confidence: number;
    risk: number;
    opportunity: number;
  };
  data_as_of?: string;
}

interface OpportunityListProps {
  items: SignalSummary[];
  emptyMessage?: string;
  showContractCost?: boolean;
  highlightBudget?: boolean;
  moduleLinkBase?: string;
}

export function OpportunityList({
  items,
  emptyMessage,
  showContractCost,
  highlightBudget,
  moduleLinkBase,
}: OpportunityListProps) {
  if (items.length === 0) {
    return <EmptyState title="No signals yet" description={emptyMessage} compact />;
  }

  return (
    <div className="space-y-3">
      {items.map((item, index) => {
        const budget = Boolean(
          item.is_budget ?? (item.contract_cost != null && item.contract_cost <= 100),
        );
        return (
          <div
            key={item.id}
            className={`atlas-card atlas-card-interactive p-4 sm:p-5 ${
              budget && highlightBudget
                ? "border-emerald-500/50 ring-2 ring-emerald-500/20"
                : ""
            }`}
          >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs uppercase tracking-wide text-muted">
                  #{index + 1} · {item.module}
                </p>
                {budget && highlightBudget && <BudgetTag cost={item.contract_cost} />}
              </div>
              <h3 className="mt-1 font-semibold">{item.title}</h3>
              {showContractCost && item.contract_cost != null && (
                <p className="mt-0.5 text-sm font-medium text-success">
                  ${Number(item.contract_cost).toFixed(0)} per contract
                </p>
              )}
              <p className="mt-1 text-sm text-muted line-clamp-2">{item.recommendation}</p>
              {item.context && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.context.profit_probability != null && (
                    <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-medium text-success">
                      {Number(item.context.profit_probability).toFixed(0)}% win prob
                    </span>
                  )}
                  {item.context.rsi != null && (
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                      RSI {Number(item.context.rsi).toFixed(0)}
                    </span>
                  )}
                  {item.context.relative_volume != null && (
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                      Vol {Number(item.context.relative_volume).toFixed(1)}x
                    </span>
                  )}
                  {item.context.has_catalyst && (
                    <span className="rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                      📰 News catalyst
                    </span>
                  )}
                  {item.context.expected_value != null && (
                    <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-medium text-success">
                      EV {Number(item.context.expected_value) >= 0 ? "+" : ""}
                      {Number(item.context.expected_value).toFixed(1)}%
                    </span>
                  )}
                  {item.context.edge_pct != null && (
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                      Edge {Number(item.context.edge_pct).toFixed(1)}%
                    </span>
                  )}
                  {item.context.trend_bullish === false && (
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                      Bearish trend
                    </span>
                  )}
                </div>
              )}
              {item.context?.top_headline && (
                <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">
                    Catalyst news
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-foreground line-clamp-3">
                    {item.context.top_headline}
                  </p>
                </div>
              )}
              {item.module === "sports" && (item.context?.book_odds?.length ?? 0) > 0 && (
                <BookOddsStrip
                  books={item.context?.book_odds ?? []}
                  preferredBook={item.context?.preferred_book ?? "fanduel"}
                  compact
                />
              )}
              {item.trade_plan?.purchase_window && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="rounded-md bg-accent/15 px-2 py-0.5 text-xs text-accent">
                    Buy {item.trade_plan.purchase_window.label}
                  </span>
                  {item.trade_plan.breakeven_price != null && (
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                      Breakeven ${Number(item.trade_plan.breakeven_price).toFixed(2)}
                    </span>
                  )}
                </div>
              )}
              <Link
                href={
                  item.module === "stock"
                    ? `${moduleLinkBase ?? "/stocks"}/${item.id}`
                    : item.module === "sports"
                      ? `/sports/${item.id}`
                      : "/options"
                }
                className="mt-2 inline-block text-xs font-medium text-accent hover:underline"
              >
                {item.module === "stock"
                  ? "View entry, stop, targets & chart →"
                  : item.module === "sports"
                    ? "View odds, edge & analysis →"
                    : "View dates, ITM odds & strategies →"}
              </Link>
            </div>
            <div className="grid grid-cols-3 gap-2 sm:min-w-[240px]">
              <ScoreBadge label="Confidence" value={item.scores.confidence} variant="confidence" />
              <ScoreBadge label="Risk" value={item.scores.risk} variant="risk" />
              <ScoreBadge label="Opportunity" value={item.scores.opportunity} variant="opportunity" />
            </div>
          </div>
          </div>
        );
      })}
    </div>
  );
}
