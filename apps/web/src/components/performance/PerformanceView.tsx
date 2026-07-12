"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { buildClientCoachInsight, type CoachInsight } from "@/lib/performance-coach";
import {
  groupBySector,
  gradedOnly,
  isAtlasOnlyLane,
  isUserLane,
  pendingOnly,
  resolvePickOrigin,
} from "@/lib/performance-origin";
import {
  backfillPerformanceTracking,
  fetchPerformanceHistory,
  fetchPerformanceSummary,
  formatWatchlistSyncMessage,
  syncWatchlistToPerformance,
  updatePerformanceOutcome,
} from "@/lib/performance-api";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface PerformanceEntry {
  id: string;
  module: string;
  signal_id: string;
  outcome: string;
  return_pct?: number | null;
  hold_duration_hours?: number | null;
  logged_at?: string;
  resolution_source?: string | null;
  signal_label?: string | null;
  pick_origin?: string | null;
  graded_by?: string | null;
}

export interface PerformanceSummary {
  days: number;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  avg_loss_pct?: number | null;
  total_signals?: number;
  wins?: number;
  losses?: number;
  scratches?: number;
  pending?: number;
  auto_resolved?: number;
  atlas_picks?: number;
  user_picks?: number;
  learning_active?: boolean;
  learning_notes?: string[];
  confidence_accuracy?: Record<string, { count: number; win_rate: number }>;
  market_learning?: {
    headline?: string;
    active_markets?: number;
    markets?: Array<{
      id: string;
      label: string;
      decided: number;
      win_rate: number | null;
      maturity: string;
      maturity_label: string;
      adjustment: string;
      feeds_next_picks?: boolean;
      details?: string[];
    }>;
    web_sources?: {
      decided?: number;
      win_rate?: number | null;
      note?: string | null;
      summary?: string;
      examples?: Array<{ title?: string; url?: string; provider?: string }>;
    };
  };
  sports_learning?: Record<string, unknown>;
  calibration?: {
    sample_count?: number;
    learning_notes?: string[];
    active?: boolean;
    market_learning?: PerformanceSummary["market_learning"];
  };
  by_module?: Record<string, PerformanceSummary>;
}

interface PerformanceViewProps {
  initialSummary: PerformanceSummary;
  initialHistory: PerformanceEntry[];
}

const SECTORS = [
  { id: "sports", label: "Sports", canAutoGrade: true },
  { id: "stock", label: "Stocks", canAutoGrade: true },
  { id: "options", label: "Options", canAutoGrade: true },
  { id: "parlay", label: "Parlays", canAutoGrade: true },
] as const;

type SectorId = (typeof SECTORS)[number]["id"];

const HISTORY_LIMIT = 1000;
const ATLAS_PREVIEW = 6;

export function PerformanceView({ initialSummary, initialHistory }: PerformanceViewProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [history, setHistory] = useState(initialHistory);
  const [loading, setLoading] = useState(false);
  const [gradingSector, setGradingSector] = useState<SectorId | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [coachInsight, setCoachInsight] = useState<CoachInsight | null>(() =>
    buildClientCoachInsight(initialSummary),
  );
  const [coachRefreshing, setCoachRefreshing] = useState(false);
  const [coachError, setCoachError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"api" | "direct" | null>(null);
  const [atlasExpanded, setAtlasExpanded] = useState(false);
  const [showMyGraded, setShowMyGraded] = useState(false);
  const didBootstrap = useRef(false);
  const syncInFlight = useRef(false);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  const refreshSummary = useCallback(async () => {
    const token = await getToken();
    const creds = usesBffProxy() ? "include" : ("same-origin" as RequestCredentials);

    let usedApi = false;
    try {
      const [sumRes, histRes] = await Promise.all([
        fetch(`${getApiUrl()}/performance/summary?days=30`, {
          headers: apiRequestHeaders(token),
          cache: "no-store",
          credentials: creds,
        }),
        fetch(`${getApiUrl()}/performance/history?limit=${HISTORY_LIMIT}`, {
          headers: apiRequestHeaders(token),
          cache: "no-store",
          credentials: creds,
        }),
      ]);
      if (sumRes.ok && histRes.ok) {
        setSummary(await sumRes.json());
        const data = await histRes.json();
        setHistory(data.items ?? []);
        setDataSource("api");
        usedApi = true;
      }
    } catch {
      /* fall through */
    }

    if (!usedApi) {
      const [sum, hist] = await Promise.all([
        fetchPerformanceSummary(30),
        fetchPerformanceHistory(HISTORY_LIMIT),
      ]);
      setSummary(sum);
      setHistory(hist);
      setDataSource("direct");
    }
  }, []);

  const loadCoachInsight = useCallback(
    async (refresh = false) => {
      const snapshot = summary;
      setCoachInsight(buildClientCoachInsight(snapshot));
      setCoachError(null);
      if (refresh) setCoachRefreshing(true);

      const token = await getToken();
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 12_000);

      try {
        const params = new URLSearchParams({ days: "30" });
        if (refresh) params.set("refresh", "true");
        const res = await fetch(`${getApiUrl()}/ai/coach-insight?${params}`, {
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
          signal: controller.signal,
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok && body.narrative) {
          setCoachInsight(body);
        } else if (!res.ok) {
          const detail = typeof body.detail === "string" ? body.detail : null;
          if (detail && !detail.toLowerCase().includes("not found")) {
            setCoachError(`Using offline coach — ${detail}`);
          }
        }
      } catch (err) {
        const aborted = err instanceof Error && err.name === "AbortError";
        if (aborted || refresh) {
          setCoachError("Using offline coach — API took too long or is unavailable.");
        }
      } finally {
        window.clearTimeout(timeout);
        setCoachRefreshing(false);
      }
    },
    [summary],
  );

  const syncWatchlist = useCallback(
    async (silent = true) => {
      if (syncInFlight.current) {
        return {
          synced: 0,
          skipped: 0,
          alreadyTracked: 0,
          total: 0,
          trackable: 0,
          errors: [],
          source: "direct" as const,
        };
      }
      syncInFlight.current = true;
      if (!silent) {
        setLoading(true);
        setMessage(null);
      }
      try {
        const result = await syncWatchlistToPerformance();
        await refreshSummary();
        if (!silent) {
          void loadCoachInsight(true);
        }
        if (result.source === "direct") {
          setDataSource("direct");
        }
        if (!silent || result.synced > 0) {
          setMessage(formatWatchlistSyncMessage(result));
        }
        return result;
      } catch (err) {
        if (!silent) {
          setMessage(err instanceof Error ? err.message : "Watchlist sync failed");
        }
        return {
          synced: 0,
          skipped: 0,
          alreadyTracked: 0,
          total: 0,
          trackable: 0,
          errors: [],
          source: "direct" as const,
        };
      } finally {
        syncInFlight.current = false;
        if (!silent) setLoading(false);
      }
    },
    [loadCoachInsight, refreshSummary],
  );

  const runBackfill = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      if (!silent) setMessage(null);
      try {
        const result = await backfillPerformanceTracking();
        if (result.source === "direct") {
          setDataSource("direct");
        }
        const registered = result.registered;
        const parts = Object.entries(result.by_module)
          .filter(([, v]) => (v?.registered ?? 0) > 0)
          .map(([k, v]) => `${k}: ${v?.registered}`);
        if (!silent || registered > 0) {
          const via = result.source === "direct" ? " (saved directly)" : "";
          setMessage(
            registered > 0
              ? `Registered ${registered} pick(s) for tracking${via}${parts.length ? ` — ${parts.join(", ")}` : ""}`
              : "All past picks are already tracked — try Grade on a sector below",
          );
        }
        await refreshSummary();
        if (!silent) void loadCoachInsight(true);
      } catch (err) {
        if (!silent) {
          setMessage(err instanceof Error ? err.message : "Could not register past picks");
        }
      }
      if (!silent) setLoading(false);
    },
    [loadCoachInsight, refreshSummary],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (didBootstrap.current) return;
      didBootstrap.current = true;

      // 1) Pull every watchlist pick into performance
      const sync = await syncWatchlist(true);
      if (cancelled) return;

      // 2) Register any scanned picks missing from performance
      await runBackfill(true);
      if (cancelled) return;

      // 3) Auto-grade settled sports/stocks/options/parlays (high limit)
      try {
        const token = await getToken();
        await fetch(`${getApiUrl()}/engine/resolve-outcomes?limit=80`, {
          method: "POST",
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
        });
      } catch {
        /* non-fatal */
      }
      if (cancelled) return;

      await refreshSummary();
      if (cancelled) return;
      void loadCoachInsight(false);

      if (!silentMessageNeeded(sync)) return;
      setMessage(formatWatchlistSyncMessage(sync));
    })();

    function onUpdated() {
      void refreshSummary();
    }
    function onWatchlistUpdated() {
      void syncWatchlist(true).then(() => refreshSummary());
    }
    window.addEventListener("atlas:performance-updated", onUpdated);
    window.addEventListener("atlas:watchlist-updated", onWatchlistUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener("atlas:performance-updated", onUpdated);
      window.removeEventListener("atlas:watchlist-updated", onWatchlistUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setCoachInsight(buildClientCoachInsight(summary));
  }, [summary]);

  const userPicks = useMemo(() => history.filter(isUserLane), [history]);
  const atlasPicks = useMemo(() => history.filter(isAtlasOnlyLane), [history]);

  const userPending = useMemo(() => pendingOnly(userPicks), [userPicks]);
  const userGraded = useMemo(() => gradedOnly(userPicks), [userPicks]);

  const userPendingBySector = useMemo(() => groupBySector(userPending), [userPending]);
  const userGradedBySector = useMemo(() => groupBySector(userGraded), [userGraded]);
  const atlasBySector = useMemo(() => groupBySector(atlasPicks), [atlasPicks]);

  const laneStats = useMemo(() => {
    function stats(rows: PerformanceEntry[]) {
      const graded = rows.filter((r) => ["win", "loss", "scratch"].includes(r.outcome));
      const wins = graded.filter((r) => r.outcome === "win").length;
      const losses = graded.filter((r) => r.outcome === "loss").length;
      const pending = rows.filter((r) => r.outcome === "pending").length;
      const decided = wins + losses;
      const winRate = decided > 0 ? Math.round((wins / decided) * 1000) / 10 : null;
      return { total: rows.length, graded: graded.length, wins, losses, pending, winRate };
    }
    return { user: stats(userPicks), atlas: stats(atlasPicks) };
  }, [userPicks, atlasPicks]);

  function silentMessageNeeded(sync: {
    synced: number;
    alreadyTracked: number;
    total: number;
  }) {
    return sync.synced > 0;
  }

  async function runResolveAll() {
    setGradingSector("sports");
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/engine/resolve-outcomes?limit=80`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        const resolved = body.resolved ?? 0;
        setMessage(
          resolved > 0
            ? `Auto-graded ${resolved} settled pick(s) across all sectors`
            : "No new grades ready — games/expirations still open",
        );
        await refreshSummary();
        void loadCoachInsight(true);
      } else {
        setMessage(typeof body.detail === "string" ? body.detail : "Could not auto-grade");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setGradingSector(null);
  }

  async function runResolveSector(sectorId: SectorId) {
    setGradingSector(sectorId);
    setMessage(null);
    const token = await getToken();
    const sector = SECTORS.find((s) => s.id === sectorId);
    try {
      const params = new URLSearchParams({ module: sectorId, limit: "80" });
      const res = await fetch(`${getApiUrl()}/engine/resolve-outcomes?${params}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        const resolved = body.resolved ?? 0;
        const skipped = body.skipped ?? 0;
        const modResult = body.by_module?.[sectorId] as { resolved?: number; pending?: number } | undefined;
        let msg =
          resolved > 0
            ? `Auto-graded ${resolved} ${sector?.label.toLowerCase() ?? sectorId} pick(s)`
            : skipped > 0
              ? `No new grades — ${skipped} ${sector?.label.toLowerCase() ?? sectorId} pick(s) still awaiting final data`
              : `No ${sector?.label.toLowerCase() ?? sectorId} picks ready to grade yet`;
        if (modResult && resolved === 0 && (modResult.pending ?? 0) > 0) {
          msg += ` (${modResult.pending} pending in this sector)`;
        }
        setMessage(msg);
        await refreshSummary();
        void loadCoachInsight(true);
      } else {
        const detail = typeof body.detail === "string" ? body.detail : "Could not auto-grade picks";
        setMessage(detail);
      }
    } catch {
      setMessage("Backend not responding");
    }
    setGradingSector(null);
  }

  async function runAggregate() {
    setLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/engine/coach-aggregate`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      const body = await res.json();
      if (res.ok && body.summary) {
        setSummary(body.summary);
        setMessage("Performance summary updated");
        void loadCoachInsight(true);
      } else {
        setMessage("Aggregate failed");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setLoading(false);
  }

  const learningNotes = summary.learning_notes ?? summary.calibration?.learning_notes ?? [];
  const confidenceBuckets = summary.confidence_accuracy ?? {};
  const marketLearning =
    summary.market_learning ?? summary.calibration?.market_learning ?? { markets: [], headline: "" };

  return (
    <div className="space-y-8">
      <LearningLoopPanel marketLearning={marketLearning} learningActive={Boolean(summary.learning_active)} />

      <section className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
        <h2 className="text-sm font-semibold text-foreground">How Atlas learns</h2>
        <p className="mt-2 text-sm text-muted">
          Every graded result — your picks and Atlas board picks — teaches the next scan across sports,
          stocks, options, and parlays. Thresholds tighten where results are weak and lean into what is
          hitting.
        </p>
        {learningNotes.length > 0 ? (
          <ul className="mt-3 space-y-1 text-sm text-violet-200">
            {learningNotes.slice(0, 6).map((note) => (
              <li key={note}>· {note}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-xs text-muted">
            Grade settled picks (or open Sports so finished games auto-grade) to start the loop.
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void loadCoachInsight(true)}
            disabled={loading || coachRefreshing}
            className="rounded-lg border border-sky-500/40 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/10 disabled:opacity-50"
          >
            {coachRefreshing ? "Refreshing coach…" : "Refresh coach insight"}
          </button>
          <button
            type="button"
            onClick={() => void syncWatchlist(false)}
            disabled={loading}
            className="rounded-lg border border-violet-500/40 px-4 py-2 text-sm font-medium text-violet-200 hover:bg-violet-500/10 disabled:opacity-50"
          >
            Sync watchlist picks
          </button>
          <button
            type="button"
            onClick={() => void runBackfill(false)}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-surface-hover disabled:opacity-50"
          >
            Register all Atlas picks
          </button>
          <button
            type="button"
            onClick={() => void runResolveAll()}
            disabled={loading || gradingSector != null}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {gradingSector ? "Grading…" : "Grade all settled"}
          </button>
          <button
            type="button"
            onClick={runAggregate}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-surface-hover disabled:opacity-50"
          >
            Refresh summary
          </button>
        </div>

        <div className="mt-4 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">
              {coachInsight?.source === "openai" ? "AI coach" : "Coach summary"}
            </p>
            {coachRefreshing && (
              <span className="text-xs text-muted">Updating…</span>
            )}
          </div>
          {coachError && (
            <p className="mt-2 text-xs text-amber-300/90">{coachError}</p>
          )}
          {coachInsight?.narrative ? (
            <>
              <p className="mt-2 text-sm leading-relaxed text-foreground/90">{coachInsight.narrative}</p>
              {coachInsight.focus_areas && coachInsight.focus_areas.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm text-muted">
                  {coachInsight.focus_areas.map((area) => (
                    <li key={area}>· {area}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="mt-2 text-sm text-muted">
              Grade a few settled picks to unlock personalized coaching.
            </p>
          )}
        </div>

        {message && <p className="mt-3 text-sm text-muted">{message}</p>}
        {dataSource === "direct" && (
          <p className="mt-2 text-xs text-amber-300/80">
            Tracking via Supabase directly — API backend unreachable. Grading and saves still work.
          </p>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <LaneSummaryCard
          title="Your picks"
          subtitle="Watchlist saves & picks you acted on"
          accent="emerald"
          stats={laneStats.user}
          active
        />
        <button
          type="button"
          onClick={() => setAtlasExpanded((v) => !v)}
          className={`rounded-xl border p-4 text-left transition-colors ${
            atlasExpanded
              ? "border-sky-500/50 bg-sky-500/10"
              : "border-border bg-surface hover:border-sky-500/30"
          }`}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-300">Atlas scan picks</p>
          <p className="mt-1 text-sm text-muted">
            Auto-tracked for learning — not shown in your waiting list
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-sm">
            <span>
              <strong className="text-2xl text-foreground">{laneStats.atlas.total}</strong>
              <span className="ml-1 text-muted">tracked</span>
            </span>
            {laneStats.atlas.winRate != null && (
              <span className="text-muted">
                Win rate <strong className="text-foreground">{laneStats.atlas.winRate}%</strong>
              </span>
            )}
            {laneStats.atlas.pending > 0 && (
              <span className="text-muted">
                <strong className="text-sky-300">{laneStats.atlas.pending}</strong> open
              </span>
            )}
          </div>
          <p className="mt-3 text-xs font-medium text-sky-300">
            {atlasExpanded ? "Hide Atlas scan history ↑" : `Show all ${laneStats.atlas.total} Atlas scan picks ↓`}
          </p>
        </button>
      </section>

      <PickOriginLane
        title="Waiting to be graded"
        subtitle="Only your watchlist / logged picks — Atlas board picks grade in the background for learning"
        accent="emerald"
        picksBySector={userPendingBySector}
        summary={summary}
        coachInsight={coachInsight}
        gradingSector={gradingSector}
        onGrade={(id) => void runResolveSector(id)}
        onUpdated={refreshSummary}
        emptyHint={
          <>
            Nothing waiting — save plays from Sports, Stocks, Options, or Parlays to your{" "}
            <Link href="/watchlist" className="text-accent hover:underline">
              watchlist
            </Link>{" "}
            and they show up here until graded.
          </>
        }
      />

      {userGraded.length > 0 && (
        <section className="rounded-xl border border-border bg-surface/40 p-4">
          <button
            type="button"
            onClick={() => setShowMyGraded((v) => !v)}
            className="flex w-full items-center justify-between text-left"
          >
            <div>
              <h2 className="text-base font-semibold">Your graded results</h2>
              <p className="mt-0.5 text-sm text-muted">
                {userGraded.length} settled pick{userGraded.length === 1 ? "" : "s"} you tracked
              </p>
            </div>
            <span className="text-xs font-medium text-emerald-300">
              {showMyGraded ? "Hide ↑" : "Show ↓"}
            </span>
          </button>
          {showMyGraded && (
            <div className="mt-4">
              <PickOriginLane
                title="Your graded results"
                subtitle="Wins, losses, and scratches from picks you saved or logged"
                accent="emerald"
                picksBySector={userGradedBySector}
                summary={summary}
                coachInsight={coachInsight}
                gradingSector={gradingSector}
                onGrade={(id) => void runResolveSector(id)}
                onUpdated={refreshSummary}
                emptyHint="No graded picks yet."
                hideHeader
              />
            </div>
          )}
        </section>
      )}

      {atlasExpanded && (
        <PickOriginLane
          title="Atlas scan picks"
          subtitle="Board picks Atlas presented — auto-graded for learning; not mixed into your waiting list"
          accent="sky"
          picksBySector={atlasBySector}
          summary={summary}
          coachInsight={coachInsight}
          gradingSector={gradingSector}
          onGrade={(id) => void runResolveSector(id)}
          onUpdated={refreshSummary}
          previewLimit={ATLAS_PREVIEW}
          emptyHint="Run a market scan on Sports, Stocks, or Options — Atlas auto-tracks every ranked signal here."
        />
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Your picks" value={String(laneStats.user.total)} />
        <StatCard
          label="Your win rate"
          value={laneStats.user.winRate != null ? `${laneStats.user.winRate}%` : "—"}
        />
        <StatCard label="Atlas scans tracked" value={String(laneStats.atlas.total)} />
        <StatCard
          label="Atlas win rate"
          value={laneStats.atlas.winRate != null ? `${laneStats.atlas.winRate}%` : "—"}
        />
      </section>

      {Object.keys(confidenceBuckets).length > 0 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Confidence vs actual results</h2>
          <p className="mt-1 text-xs text-muted">
            When Atlas is overconfident in a bucket, future scans adjust scores automatically.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(confidenceBuckets).map(([label, bucket]) => (
              <div key={label} className="rounded-lg border border-border bg-background/50 p-3">
                <p className="text-xs text-muted">Confidence {label}</p>
                <p className="mt-1 text-lg font-semibold">{bucket.win_rate}% win</p>
                <p className="text-xs text-muted">{bucket.count} picks</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function LearningLoopPanel({
  marketLearning,
  learningActive,
}: {
  marketLearning: NonNullable<PerformanceSummary["market_learning"]>;
  learningActive: boolean;
}) {
  const markets = marketLearning.markets ?? [];
  const maturityTone = (m: string) => {
    if (m === "active") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    if (m === "warming") return "border-sky-500/40 bg-sky-500/10 text-sky-200";
    if (m === "seeding") return "border-amber-500/40 bg-amber-500/10 text-amber-100";
    return "border-border bg-surface/60 text-muted";
  };

  return (
    <section className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-emerald-500/10 via-transparent to-sky-500/5 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300/90">
            Atlas learning loop
          </p>
          <h2 className="mt-1 text-base font-semibold text-foreground">
            {learningActive ? "Adapting from real market results" : "Building market memory"}
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-muted">
            {marketLearning.headline ||
              "Each graded sports, stock, options, and parlay result feeds the next set of picks."}
          </p>
        </div>
        {typeof marketLearning.active_markets === "number" && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-center">
            <p className="text-2xl font-semibold text-foreground">{marketLearning.active_markets}</p>
            <p className="text-[11px] text-muted">markets calibrating</p>
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {markets.map((m) => (
          <div
            key={m.id}
            className={`rounded-lg border p-3 ${maturityTone(m.maturity)}`}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-foreground">{m.label}</p>
              <span className="text-[10px] font-medium uppercase tracking-wide opacity-90">
                {m.maturity_label}
              </span>
            </div>
            <p className="mt-2 text-2xl font-semibold text-foreground">
              {m.win_rate != null ? `${m.win_rate}%` : "—"}
            </p>
            <p className="text-xs opacity-80">{m.decided} graded outcome{m.decided === 1 ? "" : "s"}</p>
            <p className="mt-2 text-xs leading-relaxed text-foreground/85">{m.adjustment}</p>
            {m.details && m.details.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-[11px] opacity-90">
                {m.details.map((d) => (
                  <li key={d}>· {d}</li>
                ))}
              </ul>
            )}
            {m.feeds_next_picks && (
              <p className="mt-2 text-[10px] font-medium uppercase tracking-wide opacity-70">
                Feeds next {m.label.toLowerCase()} picks
              </p>
            )}
          </div>
        ))}
      </div>

      {marketLearning.web_sources && (
        <div className="mt-4 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/90">
            Worldwide web &amp; news in the loop
          </p>
          <p className="mt-1 text-sm text-muted">
            {marketLearning.web_sources.summary ||
              "Free sports headlines and web analyst consensus feed Insight — then Atlas learns which of those picks hit."}
          </p>
          {marketLearning.web_sources.note && (
            <p className="mt-2 text-sm text-sky-100">{marketLearning.web_sources.note}</p>
          )}
          {typeof marketLearning.web_sources.decided === "number" &&
            marketLearning.web_sources.decided > 0 && (
              <p className="mt-1 text-xs text-muted">
                {marketLearning.web_sources.decided} graded news/web-backed sports picks
                {marketLearning.web_sources.win_rate != null
                  ? ` · ${marketLearning.web_sources.win_rate}% hit rate`
                  : ""}
              </p>
            )}
          {marketLearning.web_sources.examples && marketLearning.web_sources.examples.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-foreground/85">
              {marketLearning.web_sources.examples.slice(0, 4).map((ex) => (
                <li key={`${ex.title}-${ex.url || ""}`}>
                  ·{" "}
                  {ex.url ? (
                    <a
                      href={ex.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-accent hover:underline"
                    >
                      {ex.title}
                    </a>
                  ) : (
                    ex.title
                  )}
                  {ex.provider ? (
                    <span className="text-muted"> · {ex.provider}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function LaneSummaryCard({
  title,
  subtitle,
  accent,
  stats,
  active,
}: {
  title: string;
  subtitle: string;
  accent: "emerald" | "sky";
  stats: { total: number; winRate: number | null; pending: number; wins: number; losses: number };
  active?: boolean;
}) {
  const border = accent === "emerald" ? "border-emerald-500/50 bg-emerald-500/10" : "border-sky-500/50 bg-sky-500/10";
  const label = accent === "emerald" ? "text-emerald-300" : "text-sky-300";
  return (
    <div className={`rounded-xl border p-4 ${active ? border : "border-border bg-surface"}`}>
      <p className={`text-xs font-semibold uppercase tracking-wide ${label}`}>{title}</p>
      <p className="mt-1 text-sm text-muted">{subtitle}</p>
      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        <span>
          <strong className="text-2xl text-foreground">{stats.total}</strong>
          <span className="ml-1 text-muted">tracked</span>
        </span>
        {stats.winRate != null && (
          <span className="text-muted">
            Win rate <strong className="text-foreground">{stats.winRate}%</strong>
          </span>
        )}
        {stats.pending > 0 && (
          <span className="text-muted">
            <strong className={accent === "emerald" ? "text-emerald-300" : "text-sky-300"}>
              {stats.pending}
            </strong>{" "}
            open
          </span>
        )}
        {(stats.wins > 0 || stats.losses > 0) && (
          <span className="text-muted">
            W/L <strong className="text-foreground">{stats.wins}/{stats.losses}</strong>
          </span>
        )}
      </div>
    </div>
  );
}

function PickOriginLane({
  title,
  subtitle,
  accent,
  picksBySector,
  summary,
  coachInsight,
  gradingSector,
  onGrade,
  onUpdated,
  previewLimit,
  emptyHint,
  hideHeader = false,
}: {
  title: string;
  subtitle: string;
  accent: "emerald" | "sky";
  picksBySector: Record<SectorId, PerformanceEntry[]>;
  summary: PerformanceSummary;
  coachInsight: CoachInsight | null;
  gradingSector: SectorId | null;
  onGrade: (id: SectorId) => void;
  onUpdated: () => Promise<void>;
  previewLimit?: number;
  emptyHint: ReactNode;
  hideHeader?: boolean;
}) {
  const border = accent === "emerald" ? "border-emerald-500/40" : "border-sky-500/40";
  const headerBg = accent === "emerald" ? "bg-emerald-500/10" : "bg-sky-500/10";
  const total = SECTORS.reduce((n, s) => n + picksBySector[s.id].length, 0);

  if (total === 0) {
    if (hideHeader) return null;
    return (
      <section className={`rounded-xl border border-dashed ${border} p-6`}>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
        <p className="mt-4 text-sm text-muted">{emptyHint}</p>
      </section>
    );
  }

  return (
    <section className={`rounded-xl border ${border} overflow-hidden`}>
      {!hideHeader && (
        <div className={`border-b ${border} px-4 py-3 ${headerBg}`}>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{subtitle}</p>
          <p className="mt-1 text-xs text-muted">{total} pick{total === 1 ? "" : "s"} in this list</p>
        </div>
      )}
      <div className="space-y-4 p-4">
        {SECTORS.map((sector) => {
          const picks = picksBySector[sector.id];
          if (picks.length === 0) return null;
          const modSummary = summary.by_module?.[sector.id];
          const sectorCoach = coachInsight?.by_module?.[sector.id];
          return (
            <SectorPickBlock
              key={sector.id}
              sector={sector}
              picks={picks}
              summary={modSummary}
              coachNarrative={sectorCoach?.narrative}
              isGrading={gradingSector === sector.id}
              onGrade={() => onGrade(sector.id)}
              onUpdated={onUpdated}
              previewLimit={previewLimit}
              accent={accent}
            />
          );
        })}
      </div>
    </section>
  );
}

function SectorPickBlock({
  sector,
  picks,
  summary,
  coachNarrative,
  isGrading,
  onGrade,
  onUpdated,
  previewLimit,
  accent,
}: {
  sector: (typeof SECTORS)[number];
  picks: PerformanceEntry[];
  summary?: PerformanceSummary;
  coachNarrative?: string;
  isGrading: boolean;
  onGrade: () => void;
  onUpdated: () => Promise<void>;
  previewLimit?: number;
  accent: "emerald" | "sky";
}) {
  const [showAll, setShowAll] = useState(!previewLimit);
  const visible = previewLimit && !showAll ? picks.slice(0, previewLimit) : picks;
  const hidden = picks.length - visible.length;
  const gradedCount = picks.filter((p) => ["win", "loss", "scratch"].includes(p.outcome)).length;
  const openCount = picks.filter((p) => p.outcome === "pending").length;
  const chip =
    accent === "emerald"
      ? "bg-emerald-500/15 text-emerald-300"
      : "bg-sky-500/15 text-sky-300";

  return (
    <div className="rounded-lg border border-border/80 bg-surface/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${chip}`}>
            {sector.label}
          </span>
          <span className="text-sm text-muted">
            {picks.length} pick{picks.length === 1 ? "" : "s"}
            {summary?.win_rate != null && (
              <span className="ml-2">
                · {summary.win_rate}% win
              </span>
            )}
            {openCount > 0 && (
              <span className="ml-2 text-sky-300/90">{openCount} open</span>
            )}
          </span>
        </div>
        {sector.canAutoGrade && (
          <button
            type="button"
            onClick={onGrade}
            disabled={isGrading}
            className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted hover:bg-surface-hover disabled:opacity-50"
          >
            {isGrading ? "Grading…" : "Grade"}
          </button>
        )}
      </div>
      {coachNarrative && (
        <p className="border-b border-border/40 px-3 py-2 text-xs text-sky-200/80">{coachNarrative}</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-background/40 text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Pick</th>
              <th className="px-3 py-2">Outcome</th>
              <th className="px-3 py-2">Return</th>
              <th className="px-3 py-2">Logged</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <OutcomeRow key={row.id} row={row} onUpdated={onUpdated} sector={sector.id} compact />
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <div className="border-t border-border/60 px-3 py-2">
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="text-xs font-medium text-accent hover:underline"
          >
            Show {hidden} more {sector.label.toLowerCase()} scan pick{hidden === 1 ? "" : "s"}
          </button>
        </div>
      )}
      {gradedCount === 0 && openCount > 0 && (
        <p className="border-t border-border/40 px-3 py-2 text-xs text-muted">
          Auto-grades when the event or expiration window closes.
        </p>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v}%`;
}

function OutcomeRow({
  row,
  onUpdated,
  sector,
  compact = false,
}: {
  row: PerformanceEntry;
  onUpdated: () => Promise<void>;
  sector: SectorId;
  compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [outcome, setOutcome] = useState(row.outcome);
  const [returnPct, setReturnPct] = useState(
    row.return_pct != null ? String(row.return_pct) : "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const origin = resolvePickOrigin(row);
  const isPending = row.outcome === "pending";
  const autoGraded =
    Boolean(row.graded_by) ||
    (String(row.resolution_source ?? "").startsWith("auto_") &&
      row.resolution_source !== "auto_scan");
  const cellPad = compact ? "px-3 py-2" : "px-4 py-2";

  useEffect(() => {
    setOutcome(row.outcome);
    setReturnPct(row.return_pct != null ? String(row.return_pct) : "");
  }, [row.id, row.outcome, row.return_pct]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const returnVal = returnPct.trim() !== "" ? Number(returnPct) : undefined;
      const saved = await updatePerformanceOutcome(row.id, {
        outcome,
        returnPct: returnVal,
      });
      if (!saved) {
        throw new Error("Update failed");
      }
      setEditing(false);
      await onUpdated();
      window.dispatchEvent(new CustomEvent("atlas:performance-updated"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update outcome");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="border-b border-border/50 align-top">
      <td className={cellPad}>
        <p className="text-foreground">{row.signal_label ?? row.signal_id.slice(0, 8)}</p>
        {origin === "both" && (
          <p className="mt-0.5 text-[10px] text-violet-300/90">Also in Atlas scan</p>
        )}
        {isPending && (
          <LogOutcomeButtons
            module={sector}
            signalId={row.signal_id}
            compact
            className="mt-2"
          />
        )}
      </td>
      <td className={cellPad}>
        {editing ? (
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-sm capitalize"
          >
            <option value="win">Win</option>
            <option value="loss">Loss</option>
            <option value="scratch">Scratch</option>
            <option value="pending">Pending</option>
          </select>
        ) : (
          <span className={`capitalize ${isPending ? "text-sky-300" : ""}`}>
            {row.outcome}
            {autoGraded && <span className="ml-1 text-xs text-muted">(auto)</span>}
            {(row.resolution_source === "manual" || row.resolution_source === "manual_edit") && (
              <span className="ml-1 text-xs text-muted">(you)</span>
            )}
          </span>
        )}
      </td>
      <td className={cellPad}>
        {editing ? (
          <input
            type="number"
            step="0.1"
            placeholder="Return %"
            value={returnPct}
            onChange={(e) => setReturnPct(e.target.value)}
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm"
          />
        ) : (
          fmtPct(row.return_pct)
        )}
      </td>
      <td className={cellPad}>
        <div className="flex flex-col gap-1">
          <span className="text-muted text-xs">
            {row.logged_at ? new Date(row.logged_at).toLocaleDateString() : "—"}
          </span>
          {editing ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setOutcome(row.outcome);
                  setReturnPct(row.return_pct != null ? String(row.return_pct) : "");
                  setError(null);
                }}
                className="text-xs text-muted hover:underline"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-left text-xs font-medium text-accent hover:underline"
            >
              Edit
            </button>
          )}
          {error && <span className="text-xs text-danger">{error}</span>}
        </div>
      </td>
    </tr>
  );
}
