"use client";

import Link from "next/link";
import { useState } from "react";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { BookOddsStrip, type BookOddsLine } from "@/components/sports/BookOddsStrip";
import { SportsNewsPanel, type SportsNewsItem } from "@/components/sports/SportsNewsPanel";
import { ParlayLegToggle } from "@/components/sports/ManualParlayBuilder";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { PickPerformanceBadge } from "@/components/performance/PickPerformanceBadge";
import { AtlasExplainButton } from "@/components/ai/AtlasExplainButton";
import { AnalystPickSection } from "@/components/sports/AnalystPickSection";
import { sportBetMetadata } from "@/lib/watchlist-api";
import { CATEGORY_SLUG_LABELS } from "@/lib/sports-categories";
import { getSportMeta } from "@/lib/sport-meta";

export interface SportsSignal {
  id: string;
  sport: string;
  event_name: string;
  event_start?: string | null;
  bet_type: string;
  selection: string;
  odds_american: number;
  odds_decimal: number;
  expected_value: number;
  recommendation: string;
  explanation: string;
  confidence_score: number;
  risk_score: number;
  opportunity_score: number;
  line_movement?: {
    edge_pct?: number;
    consensus_books?: number;
    opening_odds?: number;
    book_odds?: BookOddsLine[];
    preferred_book?: string;
    source?: string;
  };
  book_odds?: BookOddsLine[];
  preferred_book?: string;
  preferred_book_title?: string;
  categories?: string[];
  related_news?: SportsNewsItem[];
  analysis_summary?: string | null;
  news_count?: number;
  news_verified?: boolean;
  timing_tier?: string | null;
  implied_prob?: number;
  sharp_indicator?: string | null;
  stats_support?: number | null;
  pick_source?: string | null;
  openai_web?: boolean;
  user_entry?: boolean;
  scoring_snapshot?: {
    source?: string;
    openai_web?: boolean;
    user_entry?: boolean;
    pick_origin?: string;
    is_player_prop?: boolean;
    is_fight_prop?: boolean;
    prop_market?: string;
    fanduel_verified?: boolean;
    [key: string]: unknown;
  } | null;
  team_stats?: {
    summary?: string;
    form_note?: string;
    support_score?: number;
    home?: { name: string; record: string; form: string; win_pct?: number };
    away?: { name: string; record: string; form: string; win_pct?: number };
    h2h?: { home_wins: number; away_wins: number; games: number };
  } | null;
  bull_case?: string | null;
  bear_case?: string | null;
  invalidation?: string | null;
  suggested_action?: string | null;
  risk_warning?: string;
  data_as_of_label?: string | null;
  hours_until_start?: number | null;
  is_stale?: boolean;
  staleness_reason?: string | null;
  context?: {
    expected_value?: number;
    edge_pct?: number;
    sharp_indicator?: string | null;
    bet_type?: string;
  };
}

function betTypeLabel(betType: string) {
  if (betType === "moneyline") return "Moneyline";
  if (betType === "spread") return "Spread";
  if (betType === "total") return "Total";
  if (betType === "player_prop") return "Player prop";
  if (betType === "futures" || betType === "outright") return "Futures";
  return betType;
}

function kickoffBadge(hours?: number | null) {
  if (hours == null || hours <= 0) return null;
  if (hours <= 6) return { label: "Starting very soon", className: "bg-rose-500/20 text-rose-300" };
  if (hours <= 24) return { label: "Today", className: "bg-amber-500/20 text-amber-300" };
  if (hours <= 48) return { label: "Next 48h", className: "bg-emerald-500/20 text-emerald-300" };
  if (hours <= 168) return { label: "This week", className: "bg-sky-500/20 text-sky-300" };
  if (hours <= 720) return { label: "This month", className: "bg-violet-500/20 text-violet-300" };
  return { label: "Futures window", className: "bg-violet-500/15 text-violet-200" };
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

export function SportsSignalCard({
  row,
  rank,
  parlaySelected,
  onParlayToggle,
  hideSelection = false,
  showAnalystPicks = true,
  embedded = false,
}: {
  row: SportsSignal;
  rank: number;
  parlaySelected?: boolean;
  onParlayToggle?: (id: string) => void;
  hideSelection?: boolean;
  showAnalystPicks?: boolean;
  /** When true (watchlist/performance), stay in place — no origin-page link. */
  embedded?: boolean;
}) {
  const [expanded, setExpanded] = useState(rank === 1);
  const edge = row.line_movement?.edge_pct ?? row.context?.edge_pct;
  const ev = row.expected_value ?? row.context?.expected_value;
  const sharp = row.sharp_indicator ?? row.context?.sharp_indicator;
  const bookOdds = row.book_odds ?? row.line_movement?.book_odds ?? [];
  const preferredBook = row.preferred_book ?? row.line_movement?.preferred_book ?? "fanduel";
  const categories = row.categories ?? [];
  const sportMeta = getSportMeta(row.sport);
  const isTopPick = rank === 1;
  const soonBadge = kickoffBadge(row.hours_until_start);
  const showNews = Boolean(row.news_verified && (row.related_news?.length ?? 0) > 0);
  const isOpenAiPick = Boolean(
    row.openai_web
      || row.pick_source === "openai_web"
      || row.scoring_snapshot?.source === "openai_web"
      || row.scoring_snapshot?.openai_web
      || row.line_movement?.source === "openai_web",
  );
  const isMyBet = Boolean(
    row.user_entry
      || row.pick_source === "user_entry"
      || row.scoring_snapshot?.source === "user_entry"
      || row.scoring_snapshot?.user_entry
      || row.scoring_snapshot?.pick_origin === "user"
      || row.line_movement?.source === "user_entry",
  );

  return (
    <article
      className={`signal-card atlas-card atlas-card-interactive p-4 sm:p-5 ${
        isTopPick ? "border-violet-500/50 ring-2 ring-violet-500/20" : ""
      } ${isOpenAiPick ? "border-sky-500/40" : ""} ${isMyBet ? "border-orange-500/40" : ""}`}
    >
      {onParlayToggle && (
        <div className="signal-card__parlay-toggle">
          <ParlayLegToggle
            signalId={row.id}
            selected={Boolean(parlaySelected)}
            onToggle={onParlayToggle}
          />
        </div>
      )}

      <div className={`signal-card__meta w-full min-w-0 ${onParlayToggle ? "pr-11 sm:pr-0" : ""}`}>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs uppercase tracking-wide text-muted">
            #{rank} · Sports{isTopPick && " · TOP PICK"}
          </p>
          {isOpenAiPick && (
            <span
              title="Atlas Insight — ranked from FanDuel-verified open markets only. Confirm the number is still posted before betting."
              className="rounded-full border border-sky-400/50 bg-sky-500/20 px-2 py-0.5 text-xs font-bold tracking-wide text-sky-200"
            >
              Atlas Insight
            </span>
          )}
          {(row.scoring_snapshot?.fanduel_verified
            || (row.line_movement as { fanduel_verified?: boolean } | undefined)?.fanduel_verified) && (
            <span
              title="Matched to an open FanDuel market from The Odds API — not an invented line."
              className="rounded-full border border-emerald-400/50 bg-emerald-500/15 px-2 py-0.5 text-xs font-bold tracking-wide text-emerald-200"
            >
              FanDuel verified
            </span>
          )}
          {(row.bet_type === "player_prop"
            || row.scoring_snapshot?.is_player_prop
            || row.scoring_snapshot?.is_fight_prop) && (
            <span
              title="Prop pick — verify the live FanDuel/DraftKings line (includes MMA round totals)."
              className="rounded-full border border-fuchsia-400/50 bg-fuchsia-500/20 px-2 py-0.5 text-xs font-bold tracking-wide text-fuchsia-100"
            >
              Prop
            </span>
          )}
          {isMyBet && (
            <span
              title="You logged this bet — Atlas tracks and grades it to improve learning."
              className="rounded-full border border-orange-400/50 bg-orange-500/20 px-2 py-0.5 text-xs font-bold tracking-wide text-orange-100"
            >
              My bet
            </span>
          )}
          <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${sportMeta.accentClass}`}>
            {sportMeta.emoji} {sportMeta.label}
          </span>
          <span className="rounded-full bg-background px-2 py-0.5 text-xs text-muted">
            {betTypeLabel(row.bet_type)}
          </span>
          {soonBadge && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${soonBadge.className}`}>
              {soonBadge.label}
            </span>
          )}
          {sharp && sharp !== "consensus" && (
            <span className="rounded-full bg-sky-500/20 px-2 py-0.5 text-xs font-medium text-sky-300">
              {sharp === "steam" ? "Steam move" : "Value"}
            </span>
          )}
          {isOpenAiPick && (
            <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-300/90">
              Analyst consensus
            </span>
          )}
          {categories.slice(0, 2).map((slug) => (
            <span
              key={slug}
              className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-300"
            >
              {CATEGORY_SLUG_LABELS[slug] ?? slug}
            </span>
          ))}
          <PickPerformanceBadge module="sports" signalId={row.id} />
        </div>
      </div>

      <div className="signal-card__body mt-3 w-full min-w-0">
        {!hideSelection && (
          <h2 className="signal-card__title text-xl font-bold leading-tight sm:text-2xl">{row.selection}</h2>
        )}
        <p className={`text-sm leading-relaxed text-muted ${hideSelection ? "" : "mt-1"}`}>
          {row.event_name}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Starts {formatEventStart(row.event_start)}
        </p>
        {row.hours_until_start != null && row.hours_until_start > 0 && (
          <p className="mt-0.5 text-xs text-emerald-400">
            {row.hours_until_start < 24
              ? `Starts in ${row.hours_until_start.toFixed(1)}h`
              : `Starts in ${(row.hours_until_start / 24).toFixed(1)} days`}
          </p>
        )}
        {row.data_as_of_label && (
          <p className="mt-0.5 text-xs text-muted">Odds as of {row.data_as_of_label}</p>
        )}
      </div>

      <div className="signal-card__scores mt-4 grid w-full grid-cols-3 gap-2">
        <ScoreBadge label="Confidence" shortLabel="Conf." value={row.confidence_score} variant="confidence" />
        <ScoreBadge label="Risk" value={row.risk_score} variant="risk" />
        <ScoreBadge label="Opportunity" shortLabel="Opp." value={row.opportunity_score} variant="opportunity" />
      </div>

      <p className="signal-card__recommendation mt-3 text-sm font-medium leading-relaxed sm:text-base">
        {row.recommendation}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-md border border-fanduel/40 bg-fanduel-muted px-2 py-1 text-xs font-medium text-fanduel-text">
          FanDuel {row.odds_american > 0 ? "+" : ""}
          {row.odds_american}
        </span>
        {ev != null && (
          <span className="rounded-md bg-success/15 px-2 py-1 text-xs font-medium text-success">
            EV {Number(ev) >= 0 ? "+" : ""}
            {Number(ev).toFixed(1)}%
          </span>
        )}
        {edge != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            Edge {Number(edge).toFixed(1)}%
          </span>
        )}
        {row.implied_prob != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            Win prob {Number(row.implied_prob).toFixed(0)}%
          </span>
        )}
        {row.stats_support != null && Math.abs(row.stats_support) >= 8 && (
          <span
            className={`rounded-md px-2 py-1 text-xs font-medium ${
              row.stats_support >= 15
                ? "bg-emerald-500/15 text-emerald-300"
                : row.stats_support <= -15
                  ? "bg-rose-500/15 text-rose-300"
                  : "bg-background text-muted"
            }`}
          >
            Form {row.stats_support >= 0 ? "+" : ""}
            {Number(row.stats_support).toFixed(0)}
          </span>
        )}
        {row.line_movement?.consensus_books != null && (
          <span className="rounded-md bg-background px-2 py-1 text-xs text-muted">
            {row.line_movement.consensus_books} books
          </span>
        )}
      </div>

      {bookOdds.length > 0 && (
        <BookOddsStrip books={bookOdds} preferredBook={preferredBook} compact={!expanded} />
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-sm font-medium text-accent hover:underline"
        >
          {expanded ? "Hide details" : "Show analysis"}
        </button>
        {!embedded && (
          <Link href={`/sports/${row.id}`} className="text-sm font-medium text-accent hover:underline">
            Full detail page →
          </Link>
        )}
        {!embedded && (
          <AddToWatchlistButton
            symbol={row.id}
            itemType="sport_bet"
            metadata={sportBetMetadata(row)}
            label="Save bet"
            variant="compact"
          />
        )}
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-border pt-4">
          {showNews ? (
            <SportsNewsPanel
              items={row.related_news ?? []}
              analysisSummary={row.analysis_summary}
              verified
            />
          ) : row.analysis_summary ? (
            <p className="rounded-xl border border-border/60 bg-surface px-4 py-3 text-sm text-muted">
              {row.analysis_summary}
            </p>
          ) : null}
          {row.team_stats?.summary && (
            <div className="rounded-xl border border-border/60 bg-surface px-4 py-3 text-sm">
              <p className="text-xs font-bold uppercase tracking-wider text-muted">Recent form & H2H</p>
              <p className="mt-1 text-foreground">{row.team_stats.summary}</p>
              {row.team_stats.home && row.team_stats.away && (
                <p className="mt-2 text-xs text-muted">
                  {row.team_stats.home.name}: {row.team_stats.home.record} ({row.team_stats.home.form}) ·{" "}
                  {row.team_stats.away.name}: {row.team_stats.away.record} ({row.team_stats.away.form})
                  {row.team_stats.h2h && row.team_stats.h2h.games > 0 && (
                    <> · H2H {row.team_stats.h2h.home_wins}-{row.team_stats.h2h.away_wins}</>
                  )}
                </p>
              )}
            </div>
          )}
          <p className="text-sm text-muted whitespace-pre-line">{row.explanation}</p>
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
          {row.risk_warning && <p className="text-xs text-muted">{row.risk_warning}</p>}
          <LogOutcomeButtons module="sports" signalId={row.id} className="pt-2 border-t border-border" />
        </div>
      )}

      {/* Always visible: Ask Atlas, then standalone Analyst backing directly under it */}
      <div className="mt-5 space-y-0 border-t border-border pt-4">
        <AtlasExplainButton module="sports" signalId={row.id} />
        {showAnalystPicks && (
          <AnalystPickSection signalId={row.id} atlasSelection={row.selection} />
        )}
      </div>
    </article>
  );
}
