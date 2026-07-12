"use client";

import Link from "next/link";
import { useState } from "react";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { BookOddsStrip, type BookOddsLine } from "@/components/sports/BookOddsStrip";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { PickPerformanceBadge } from "@/components/performance/PickPerformanceBadge";
import { parlayMetadata } from "@/lib/watchlist-api";
import { PARLAY_CATEGORY_LABELS } from "@/lib/parlay-categories";

export interface ParlayLeg {
  id?: string;
  leg_order: number;
  sport: string;
  event_name: string;
  event_start?: string | null;
  hours_until_start?: number | null;
  bet_type: string;
  selection: string;
  odds_american: number;
  book_odds?: BookOddsLine[];
  leg_reason?: string | null;
  sports_signal_id?: string | null;
  outcome?: "win" | "loss" | "scratch" | string | null;
}

export interface Parlay {
  id: string;
  name?: string | null;
  style: "conservative" | "balanced" | "aggressive" | string;
  combined_odds_american: number;
  combined_odds_decimal: number;
  expected_value: number;
  correlation_warning?: string | null;
  confidence_score: number;
  risk_score: number;
  opportunity_score: number;
  recommendation: string;
  explanation: string;
  risk_warning?: string;
  legs: ParlayLeg[];
  leg_count?: number;
  sports?: string[];
  preferred_book?: string;
  preferred_book_title?: string;
  data_as_of?: string;
  data_as_of_label?: string | null;
  categories?: string[];
  span_hours?: number | null;
  hours_to_first_leg?: number | null;
  hours_to_last_leg?: number | null;
  earliest_event_start?: string | null;
  latest_event_start?: string | null;
}

function styleLabel(style: string) {
  if (style === "conservative") return "Conservative";
  if (style === "balanced") return "Balanced";
  if (style === "aggressive") return "Aggressive";
  return style;
}

function styleColor(style: string) {
  if (style === "conservative") return "bg-emerald-500/20 text-emerald-300";
  if (style === "balanced") return "bg-sky-500/20 text-sky-300";
  if (style === "aggressive") return "bg-orange-500/20 text-orange-300";
  return "bg-background text-muted";
}

function formatEventStart(iso?: string | null) {
  if (!iso) return "TBD";
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatTimeWindow(row: Parlay) {
  const cats = row.categories ?? [];
  if (cats.includes("today")) {
    return "All legs today";
  }
  if (row.hours_to_first_leg != null && row.hours_to_last_leg != null) {
    if (row.hours_to_last_leg <= 48) {
      return `All legs within ${row.hours_to_last_leg.toFixed(0)}h`;
    }
    if (row.span_hours != null && row.span_hours > 48) {
      return `Spans ${(row.span_hours / 24).toFixed(1)} days`;
    }
  }
  if (row.earliest_event_start && row.latest_event_start) {
    return `${formatEventStart(row.earliest_event_start)} → ${formatEventStart(row.latest_event_start)}`;
  }
  return null;
}

function legOutcomeBadge(outcome?: string | null) {
  if (!outcome || outcome === "pending") return null;
  if (outcome === "win") {
    return (
      <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-300">
        Won
      </span>
    );
  }
  if (outcome === "loss") {
    return (
      <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-red-300">
        Lost
      </span>
    );
  }
  return (
    <span className="rounded-full bg-background px-2 py-0.5 text-[10px] font-semibold uppercase text-muted">
      Scratch
    </span>
  );
}

export function ParlayCard({ row, rank }: { row: Parlay; rank: number }) {
  const [expanded, setExpanded] = useState(rank === 1);

  return (
    <article className="atlas-card atlas-card-interactive w-full max-w-full overflow-hidden p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs uppercase tracking-wide text-muted">#{rank} · Parlay</p>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styleColor(row.style)}`}>
          {styleLabel(row.style)}
        </span>
        <span className="rounded-full bg-background px-2 py-0.5 text-xs text-muted">
          {row.leg_count ?? row.legs.length} legs
        </span>
        {(row.categories ?? []).map((slug) => (
          <span
            key={slug}
            className="rounded-full bg-orange-500/15 px-2 py-0.5 text-xs font-medium text-orange-300"
          >
            {PARLAY_CATEGORY_LABELS[slug] ?? slug}
          </span>
        ))}
        <PickPerformanceBadge module="parlay" signalId={row.id} />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,260px)] lg:items-start">
        <div className="min-w-0">
          <h2 className="text-xl font-bold leading-tight text-balance sm:text-2xl">
            {row.name ?? row.recommendation}
          </h2>
          {(row.sports?.length ?? 0) > 0 && (
            <p className="mt-1 text-sm leading-relaxed text-muted">{row.sports?.join(" · ")}</p>
          )}
          {formatTimeWindow(row) && (
            <p className="mt-1 text-xs text-muted">{formatTimeWindow(row)}</p>
          )}
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
        <span className="rounded-md border border-fanduel/40 bg-fanduel-muted px-2 py-1 text-xs font-medium text-fanduel-text">
          FanDuel {row.combined_odds_american > 0 ? "+" : ""}
          {row.combined_odds_american} combined
        </span>
        <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
          {Number(row.combined_odds_decimal).toFixed(2)}x
        </span>
        <span className="rounded-md bg-success/15 px-2 py-1 text-xs font-medium text-success">
          Avg EV {Number(row.expected_value) >= 0 ? "+" : ""}
          {Number(row.expected_value).toFixed(1)}%
        </span>
      </div>

      {row.correlation_warning && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">
            Correlation warning
          </p>
          <p className="mt-1 text-sm">{row.correlation_warning}</p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-sm font-medium text-accent hover:underline"
        >
          {expanded ? "Hide legs" : "Show legs"}
        </button>
        <Link href={`/parlays/${row.id}`} className="text-sm font-medium text-accent hover:underline">
          Full detail page →
        </Link>
        <AddToWatchlistButton
          symbol={row.id}
          itemType="parlay"
          metadata={parlayMetadata({ ...row, id: row.id, source: "auto" }).metadata}
          label="Save to watchlist"
          variant="compact"
        />
        <Link href="/watchlist?tab=parlays" className="text-sm font-medium text-muted hover:text-accent">
          My saved parlays →
        </Link>
      </div>

      <LogOutcomeButtons module="parlay" signalId={row.id} compact className="mt-3" />

      {expanded && (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          <p className="text-sm text-muted">{row.explanation}</p>
          {row.legs.map((leg) => (
            <div key={leg.leg_order} className="rounded-lg border border-border bg-background/50 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs uppercase tracking-wide text-muted">
                  Leg {leg.leg_order} · {leg.sport} · {leg.bet_type}
                </p>
                {legOutcomeBadge(leg.outcome)}
              </div>
              <p className="mt-1 font-semibold">{leg.selection}</p>
              <p className="text-xs text-muted">{leg.event_name}</p>
              {leg.event_start && (
                <p className="mt-0.5 text-xs text-muted">
                  Starts {formatEventStart(leg.event_start)}
                  {leg.hours_until_start != null && leg.hours_until_start > 0 && (
                    <span className="ml-1 text-orange-300/80">
                      · in{" "}
                      {leg.hours_until_start < 24
                        ? `${leg.hours_until_start.toFixed(1)}h`
                        : `${(leg.hours_until_start / 24).toFixed(1)}d`}
                    </span>
                  )}
                </p>
              )}
              <p className="mt-1 text-sm font-medium text-fanduel-text">
                FanDuel {leg.odds_american > 0 ? "+" : ""}
                {leg.odds_american}
              </p>
              {(leg.book_odds?.length ?? 0) > 0 && (
                <BookOddsStrip
                  books={leg.book_odds ?? []}
                  preferredBook={row.preferred_book ?? "fanduel"}
                  compact
                />
              )}
              {leg.leg_reason && <p className="mt-2 text-sm text-muted">{leg.leg_reason}</p>}
            </div>
          ))}
          {row.risk_warning && <p className="text-xs text-muted">{row.risk_warning}</p>}
        </div>
      )}
    </article>
  );
}
