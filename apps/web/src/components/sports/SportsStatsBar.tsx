import Link from "next/link";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import { buildSportCounts, FEATURED_LEAGUES } from "@/lib/sport-meta";

interface SportsStatsBarProps {
  items: SportsSignal[];
  cacheFresh?: boolean;
  creditsRemaining?: number | null;
}

export function SportsStatsBar({ items, cacheFresh, creditsRemaining }: SportsStatsBarProps) {
  const leagues = buildSportCounts(items);
  const nextEvent = items
    .filter((i) => i.hours_until_start != null && i.hours_until_start > 0)
    .sort((a, b) => (a.hours_until_start ?? 999) - (b.hours_until_start ?? 999))[0];

  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Live plays</p>
        <p className="mt-1 text-2xl font-bold text-foreground">{items.length}</p>
        <p className="mt-0.5 text-xs text-muted">Ranked +EV opportunities</p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Leagues active</p>
        <p className="mt-1 text-2xl font-bold text-foreground">{leagues.length || "—"}</p>
        <p className="mt-0.5 text-xs text-muted truncate">
          {leagues.length > 0
            ? leagues.slice(0, 4).map((l) => l.meta.label).join(" · ")
            : FEATURED_LEAGUES.slice(0, 5).join(" · ")}
        </p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Next game</p>
        <p className="mt-1 text-lg font-bold text-foreground">
          {nextEvent
            ? nextEvent.hours_until_start! < 24
              ? `${nextEvent.hours_until_start!.toFixed(0)}h`
              : `${(nextEvent.hours_until_start! / 24).toFixed(1)}d`
            : "—"}
        </p>
        <p className="mt-0.5 text-xs text-muted line-clamp-1">
          {nextEvent ? nextEvent.event_name : "Scan to load upcoming slate"}
        </p>
      </div>
      <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Odds feed</p>
        <p className="mt-1 text-lg font-bold text-foreground">
          {cacheFresh ? "Cached ✓" : "Needs refresh"}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {creditsRemaining != null ? `~${creditsRemaining} credits left` : "24/7 global markets"}
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
              NBA · NFL · MLB · NHL · Soccer · MMA +
            </span>
          </div>
          <h2 className="mt-3 text-xl font-bold text-foreground sm:text-2xl">
            Sports betting command center
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Atlas scans odds across leagues worldwide, ranks every play by edge and expected value,
            and links news so you know <em>why</em> a line is good — then build parlays in one click.
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
