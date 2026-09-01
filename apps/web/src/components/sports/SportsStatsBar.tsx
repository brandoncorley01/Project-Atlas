import Link from "next/link";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import { buildSportCounts, FEATURED_LEAGUES } from "@/lib/sport-meta";
import { hoursUntilStart } from "@/lib/sports-filters";
import {
  formatClockLabel,
  formatRelativeAgo,
  type SportsBoardActionKind,
} from "@/lib/sports-board-cache";

interface SportsStatsBarProps {
  items: SportsSignal[];
  cacheRescoreFree?: boolean;
  cacheFresh?: boolean;
  cacheNeedsLive?: boolean;
  creditsRemaining?: number | null;
  keyCount?: number;
  /** Last live odds cache write (Fetch). */
  oddsFetchedAt?: string | null;
  oddsAgeMinutes?: number | null;
  /** Newest pick data_as_of on the board (last scan/rescore stamp). */
  boardAsOf?: string | null;
  /** Browser-tracked last Scan / Fetch / Rescore / Insight. */
  lastActionAt?: string | null;
  lastActionKind?: SportsBoardActionKind | null;
}

function actionLabel(kind: SportsStatsBarProps["lastActionKind"]): string {
  if (kind === "live") return "Fetch";
  if (kind === "rescore") return "Rescore";
  if (kind === "openai") return "Insight";
  if (kind === "scan") return "Scan";
  return "Update";
}

export function SportsStatsBar({
  items,
  cacheRescoreFree,
  cacheFresh,
  cacheNeedsLive,
  creditsRemaining,
  keyCount,
  oddsFetchedAt,
  oddsAgeMinutes,
  boardAsOf,
  lastActionAt,
  lastActionKind,
}: SportsStatsBarProps) {
  const leagues = buildSportCounts(items);
  const nextEvent = items
    .filter((i) => {
      const h = hoursUntilStart(i);
      return h != null && h > 0;
    })
    .sort((a, b) => (hoursUntilStart(a) ?? 999) - (hoursUntilStart(b) ?? 999))[0];

  const oddsAgo = formatRelativeAgo(oddsFetchedAt);
  const oddsClock = formatClockLabel(oddsFetchedAt);
  const boardAgo = formatRelativeAgo(boardAsOf ?? lastActionAt);
  const boardClock = formatClockLabel(boardAsOf ?? lastActionAt);
  const actionAgo = formatRelativeAgo(lastActionAt);

  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Live plays</p>
        <p className="mt-1 text-2xl font-bold text-foreground">{items.length}</p>
        <p className="mt-0.5 text-xs text-muted">
          {items.length > 0
            ? "Saved on your board · stay until Scan/Rescore"
            : "Ranked +EV opportunities"}
        </p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Leagues active</p>
        <p className="mt-1 text-2xl font-bold text-foreground">{leagues.length || "—"}</p>
        <p className="mt-0.5 truncate text-xs text-muted">
          {leagues.length > 0
            ? leagues.slice(0, 4).map((l) => l.meta.label).join(" · ")
            : FEATURED_LEAGUES.slice(0, 5).join(" · ")}
        </p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">
          Last board update
        </p>
        <p className="mt-1 text-lg font-bold text-foreground">
          {boardAgo ?? (items.length > 0 ? "On board" : "—")}
        </p>
        <p className="mt-0.5 text-xs text-muted line-clamp-2">
          {lastActionAt && actionAgo
            ? `${actionLabel(lastActionKind)} ${actionAgo}${boardClock ? ` · ${boardClock}` : ""}`
            : boardClock
              ? `Picks as of ${boardClock}`
              : nextEvent
                ? nextEvent.event_name
                : "Scan or Rescore when you want fresh ranks"}
        </p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Odds feed</p>
        <p className="mt-1 text-lg font-bold text-foreground">
          {oddsAgo
            ? oddsAgo
            : cacheRescoreFree
              ? cacheFresh
                ? "Rescore free"
                : cacheNeedsLive
                  ? "Narrow cache"
                  : "Rescore free"
              : cacheFresh
                ? "Cached ✓"
                : "Needs refresh"}
        </p>
        <p className="mt-0.5 text-xs text-muted line-clamp-2">
          {oddsFetchedAt
            ? `Live odds fetched ${oddsClock ?? oddsAgo}${
                oddsAgeMinutes != null ? ` · ${Math.round(oddsAgeMinutes)}m old` : ""
              }`
            : creditsRemaining != null
              ? `${creditsRemaining.toLocaleString()} credits · ${keyCount ?? 1} key${(keyCount ?? 1) === 1 ? "" : "s"}`
              : "Fetch live odds when the slate looks stale"}
        </p>
      </div>
    </div>
  );
}

interface SportsHeroBannerProps {
  playCount?: number;
}

export function SportsHeroBanner({ playCount }: SportsHeroBannerProps) {
  return (
    <div className="mb-6 overflow-hidden rounded-2xl border border-violet-500/40 bg-gradient-to-br from-violet-600/20 via-violet-500/10 to-surface p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-violet-600 px-2.5 py-0.5 text-xs font-bold text-white">
              24/7 MARKETS
            </span>
            <span className="rounded-full border border-violet-400/40 bg-violet-500/20 px-2.5 py-0.5 text-xs font-semibold text-violet-200">
              WNBA · MLB · Soccer · Tennis · Futures +
            </span>
          </div>
          <h2 className="mt-3 text-xl font-bold text-foreground sm:text-2xl">
            Sports betting command center
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Atlas scans odds across leagues worldwide, ranks every play by edge and expected value,
            and links news so you know <em>why</em> a line is good — then build parlays in one click.
            Picks stay on your board until you Scan or Rescore.
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row lg:flex-col">
          {playCount != null && playCount > 0 && (
            <p className="rounded-xl border border-violet-400/30 bg-violet-500/15 px-4 py-3 text-center text-sm font-semibold text-violet-100">
              {playCount} plays ready · pick #1
            </p>
          )}
          <Link
            href="/parlays"
            className="rounded-xl bg-orange-500 px-4 py-3 text-center text-sm font-bold text-white shadow-md shadow-orange-500/25 hover:bg-orange-500/90"
          >
            Build parlays →
          </Link>
        </div>
      </div>
    </div>
  );
}
