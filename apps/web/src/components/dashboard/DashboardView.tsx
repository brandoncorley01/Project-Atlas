"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardSignals } from "@/components/dashboard/DashboardSignals";
import { BreakingNewsStrip } from "@/components/news/BreakingNewsStrip";
import type { NewsItem } from "@/components/news/NewsCard";
import { DataProvidersPanel } from "@/components/settings/DataProvidersPanel";
import { PlaceholderCard } from "@/components/dashboard/PlaceholderCard";
import type { SignalSummary } from "@/components/dashboard/OpportunityList";
import { ApiError, apiFetch } from "@/lib/api";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { createClient } from "@/lib/supabase/client";
import type { Parlay } from "@/components/parlays/ParlayCard";
import { ParlayCard } from "@/components/parlays/ParlayCard";
import { StaleDataBanner } from "@/components/dashboard/StaleDataBanner";
import { DashboardLoadWarnings } from "@/components/dashboard/DashboardLoadWarnings";
import { API_START_HINT } from "@/lib/api-config";
import {
  actionableWarnings,
  normalizeDashboardWarnings,
  type DashboardWarning,
} from "@/lib/dashboard-warnings";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { QuickStartGuide } from "@/components/ui/QuickStartGuide";
import { AtlasBriefingCard, type AtlasBriefing } from "@/components/dashboard/AtlasBriefingCard";
import {
  MarketIntelligenceCard,
  type MarketIntelligence,
  type TrackingStats,
} from "@/components/dashboard/MarketIntelligenceCard";

interface DashboardResponse {
  top_opportunities: SignalSummary[];
  budget_opportunities: SignalSummary[];
  stock_opportunities: SignalSummary[];
  sports_opportunities: SignalSummary[];
  best_parlay?: Parlay | null;
  breaking_news: NewsItem[];
  atlas_briefing?: AtlasBriefing | null;
  market_intelligence?: MarketIntelligence | null;
  performance_summary?: {
    win_rate_30d?: number | null;
    avg_return_30d?: number | null;
    total_logged?: number;
    learning_active?: boolean;
    learning_notes?: string[];
    auto_resolved?: number;
    tracking?: TrackingStats;
  };
  meta: {
    user_id: string;
    status: string;
    load_status?: string;
    warnings?: Array<string | DashboardWarning>;
    warning_counts?: { info?: number; warn?: number; error?: number };
    needs_refresh?: {
      sports?: boolean;
      stocks?: boolean;
      options?: boolean;
      news?: boolean;
    };
    expired_purged?: Record<string, number>;
  };
}

export function DashboardView() {
  const [loading, setLoading] = useState(true);
  const [apiRestarting, setApiRestarting] = useState(false);
  const apiRestartingRef = useRef(false);
  const loadInFlightRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const hasLoadedOnceRef = useRef(false);
  const [apiStatus, setApiStatus] = useState("Connecting to API…");
  const [apiStatusColor, setApiStatusColor] = useState("text-muted");
  const [topOpportunities, setTopOpportunities] = useState<SignalSummary[]>([]);
  const [budgetOpportunities, setBudgetOpportunities] = useState<SignalSummary[]>([]);
  const [stockOpportunities, setStockOpportunities] = useState<SignalSummary[]>([]);
  const [sportsOpportunities, setSportsOpportunities] = useState<SignalSummary[]>([]);
  const [bestParlay, setBestParlay] = useState<Parlay | null>(null);
  const [breakingNews, setBreakingNews] = useState<NewsItem[]>([]);
  const [atlasBriefing, setAtlasBriefing] = useState<AtlasBriefing | null>(null);
  const [marketIntelligence, setMarketIntelligence] = useState<MarketIntelligence | null>(null);
  const [trackingStats, setTrackingStats] = useState<TrackingStats | null>(null);
  const [briefingRefreshing, setBriefingRefreshing] = useState(false);
  const [performanceSummary, setPerformanceSummary] = useState<
    DashboardResponse["performance_summary"] | undefined
  >(undefined);
  const [freshnessMeta, setFreshnessMeta] = useState<DashboardResponse["meta"] | null>(null);
  const [loadWarnings, setLoadWarnings] = useState<DashboardWarning[]>([]);

  const loadDashboard = useCallback(async (opts?: { background?: boolean }) => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const background = opts?.background ?? hasLoadedOnceRef.current;
    if (!background) setLoading(true);

    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;

    const useBff = usesBffProxy();

    if (!useBff && !token) {
      setApiStatus("Signed out");
      setApiStatusColor("text-warning");
      setLoading(false);
      loadInFlightRef.current = false;
      return;
    }

    try {
      const dashboard = await apiFetch<DashboardResponse>("/dashboard", token, {
        signal: controller.signal,
        timeoutMs: 45_000,
      });
      setTopOpportunities(dashboard.top_opportunities ?? []);
      setBudgetOpportunities(dashboard.budget_opportunities ?? []);
      setStockOpportunities(dashboard.stock_opportunities ?? []);
      setSportsOpportunities(dashboard.sports_opportunities ?? []);
      setBestParlay(dashboard.best_parlay ?? null);
      setBreakingNews(dashboard.breaking_news ?? []);
      setAtlasBriefing(dashboard.atlas_briefing ?? null);
      setMarketIntelligence(dashboard.market_intelligence ?? null);
      setTrackingStats(dashboard.performance_summary?.tracking ?? null);
      setPerformanceSummary(dashboard.performance_summary ?? undefined);
      setFreshnessMeta(dashboard.meta ?? null);

      const warnings = normalizeDashboardWarnings(dashboard.meta?.warnings);
      setLoadWarnings(warnings);
      const actionable = actionableWarnings(warnings);
      const errorCount = actionable.filter((w) => w.severity === "error").length;
      const warnCount = actionable.filter((w) => w.severity === "warn").length;

      const total =
        (dashboard.top_opportunities?.length ?? 0) +
        (dashboard.budget_opportunities?.length ?? 0) +
        (dashboard.stock_opportunities?.length ?? 0) +
        (dashboard.sports_opportunities?.length ?? 0);

      if (errorCount > 0) {
        setApiStatus(
          `API connected · partial load (${errorCount} error${errorCount === 1 ? "" : "s"} — see details)`,
        );
        setApiStatusColor("text-warning");
      } else if (warnCount > 0 && total === 0) {
        setApiStatus(
          `API connected · partial load (${warnCount} warning${warnCount === 1 ? "" : "s"} — see details)`,
        );
        setApiStatusColor("text-warning");
      } else if (total > 0) {
        setApiStatus(
          warnCount > 0
            ? `API connected · ${total} signals · ${warnCount} notice${warnCount === 1 ? "" : "s"}`
            : `API connected · ${total} signals`,
        );
        setApiStatusColor("text-success");
      } else {
        setApiStatus("API connected · no signals yet — run a scan");
        setApiStatusColor("text-success");
      }
      hasLoadedOnceRef.current = true;
      apiRestartingRef.current = false;
      setApiRestarting(false);
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      const status = err instanceof ApiError ? err.status : (err as Error & { status?: number }).status;
      if (apiRestartingRef.current) {
        setApiStatus("API restarting — wait ~60 seconds…");
        setApiStatusColor("text-warning");
      } else if (status === 401) {
        setApiStatus("Session expired — sign out and sign in again");
        setApiStatusColor("text-danger");
      } else if (status === 404 || status === 502) {
        setApiStatus(
          err instanceof Error
            ? err.message
            : "Backend not configured — check NEXT_PUBLIC_API_URL on Vercel (must end with /api/v1)",
        );
        setApiStatusColor("text-danger");
      } else if (status === 503) {
        setApiStatus(err instanceof Error ? err.message : `Backend unreachable — ${API_START_HINT}`);
        setApiStatusColor("text-danger");
      } else if (status === 500) {
        setApiStatus(err instanceof Error ? err.message : "API server error");
        setApiStatusColor("text-danger");
      } else if (err instanceof ApiError) {
        setApiStatus(err.message);
        setApiStatusColor("text-danger");
      } else {
        setApiStatus(`Cannot reach API — ${API_START_HINT}`);
        setApiStatusColor("text-danger");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
      loadInFlightRef.current = false;
    }
  }, []);

  const refreshBriefing = useCallback(async () => {
    setBriefingRefreshing(true);
    try {
      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      const apiUrl = getApiUrl();
      try {
        await fetch(`${apiUrl}/engine/refresh-news`, {
          method: "POST",
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
          signal: AbortSignal.timeout(60_000),
        });
      } catch {
        // Still rebuild briefing from whatever is in the DB.
      }
      const briefing = await apiFetch<AtlasBriefing>("/ai/briefing?refresh=true", token, {
        timeoutMs: 45_000,
      });
      setAtlasBriefing(briefing);
      void loadDashboard({ background: true });
    } catch {
      // keep existing briefing on failure
    } finally {
      setBriefingRefreshing(false);
    }
  }, [loadDashboard]);

  useEffect(() => {
    void loadDashboard();

    function onRefresh() {
      void loadDashboard();
    }
    function onRestarting() {
      apiRestartingRef.current = true;
      setApiRestarting(true);
      abortRef.current?.abort();
      loadInFlightRef.current = false;
      setApiStatus("API restarting — wait ~60 seconds…");
      setApiStatusColor("text-warning");
      setLoading(false);
    }
    function onOnline() {
      apiRestartingRef.current = false;
      setApiRestarting(false);
      void loadDashboard({ background: false });
    }
    window.addEventListener("atlas:dashboard-refresh", onRefresh);
    window.addEventListener("atlas:api-online", onOnline);
    window.addEventListener("atlas:api-restarting", onRestarting);
    return () => {
      window.removeEventListener("atlas:dashboard-refresh", onRefresh);
      window.removeEventListener("atlas:api-online", onOnline);
      window.removeEventListener("atlas:api-restarting", onRestarting);
    };
  }, [loadDashboard]);

  useEffect(() => {
    if (apiStatusColor !== "text-danger") return;
    const id = setInterval(() => void loadDashboard({ background: true }), 15000);
    return () => clearInterval(id);
  }, [apiStatusColor, loadDashboard]);

  const hasSignals =
    topOpportunities.length > 0 ||
    budgetOpportunities.length > 0 ||
    stockOpportunities.length > 0 ||
    sportsOpportunities.length > 0;

  const hasActionableWarnings = actionableWarnings(loadWarnings).length > 0;

  const statusVariant =
    loading
      ? "loading"
      : apiRestarting
        ? "warning"
        : apiStatusColor === "text-success"
          ? hasActionableWarnings
            ? "warning"
            : "success"
          : apiStatusColor === "text-danger"
            ? "danger"
            : "warning";

  const perfLogged = performanceSummary?.total_logged ?? 0;

  return (
    <>
      <PageHeader
        title="Home"
        description={<StatusPill label={loading ? "Loading…" : apiStatus} variant={statusVariant} />}
        actions={
          !loading && apiStatusColor === "text-danger" ? (
            <button
              type="button"
              onClick={() => void loadDashboard()}
              className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-hover"
            >
              Retry connection
            </button>
          ) : undefined
        }
      />

      {loading ? (
        <DashboardSkeleton />
      ) : (
        <>
          {!hasSignals && (
            <div className="mb-5">
              <QuickStartGuide compact />
            </div>
          )}

          <DashboardLoadWarnings
            warnings={loadWarnings}
            onRetry={() => void loadDashboard()}
          />

          <StaleDataBanner meta={freshnessMeta ?? undefined} />

          <AtlasBriefingCard
            briefing={atlasBriefing}
            onRefresh={() => void refreshBriefing()}
            refreshing={briefingRefreshing}
          />

          <div className="mb-5 grid gap-3 lg:grid-cols-2">
            <div className="min-w-0 [&_section]:mb-0">
              <MarketIntelligenceCard intelligence={marketIntelligence} tracking={trackingStats} />
            </div>
            <section className="rounded-xl border border-border bg-surface/50 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Performance</h2>
                  <p className="mt-1 text-xs text-muted">
                    {perfLogged > 0
                      ? `${performanceSummary?.win_rate_30d != null ? `${performanceSummary.win_rate_30d}% win · ` : ""}${perfLogged} logged (30d)`
                      : "Log wins/losses on cards — Atlas learns."}
                  </p>
                  {performanceSummary?.learning_notes?.[0] && (
                    <p className="mt-2 text-[11px] text-violet-200/90">
                      {performanceSummary.learning_notes[0]}
                    </p>
                  )}
                </div>
                <Link href="/performance" className="text-xs font-semibold text-accent hover:underline">
                  Open →
                </Link>
              </div>
            </section>
          </div>

          <div className="mb-5 grid gap-3 sm:grid-cols-2">
            <Link
              href="/options-intelligence"
              className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 p-4 transition-colors hover:border-cyan-400/60 hover:bg-cyan-500/15"
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">New</p>
              <h2 className="mt-1 text-base font-semibold text-foreground">Options Intelligence</h2>
              <p className="mt-1 text-sm text-muted">
                Flow scanner, low-premium opportunities, concentrated activity, options heatmap.
              </p>
              <p className="mt-3 text-xs font-semibold text-cyan-300">Open Options Intel →</p>
            </Link>
            <Link
              href="/market-intelligence"
              className="rounded-xl border border-teal-500/40 bg-teal-500/10 p-4 transition-colors hover:border-teal-400/60 hover:bg-teal-500/15"
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-teal-300">New</p>
              <h2 className="mt-1 text-base font-semibold text-foreground">Market Intelligence</h2>
              <p className="mt-1 text-sm text-muted">
                Heatmaps, sector rotation, Market Weather, and swing-trade exit guidance.
              </p>
              <p className="mt-3 text-xs font-semibold text-teal-300">Open Market Intel →</p>
            </Link>
          </div>

          {breakingNews.length > 0 && (
            <section className="mb-5">
              <SectionHeader title="News" href="/news" linkLabel="All news →" />
              <BreakingNewsStrip items={breakingNews.slice(0, 6)} />
            </section>
          )}

          <DashboardSignals
            topOpportunities={topOpportunities}
            budgetOpportunities={budgetOpportunities}
            stockOpportunities={stockOpportunities}
            sportsOpportunities={sportsOpportunities}
          />

          {bestParlay && (
            <section className="mb-5">
              <SectionHeader title="Featured parlay" href="/parlays" linkLabel="All parlays →" />
              <ParlayCard row={bestParlay} rank={1} />
            </section>
          )}

          <details id="data-providers" className="mb-6 rounded-xl border border-border bg-surface/40 open:pb-3">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-foreground">
              Data providers
              <span className="ml-2 text-xs font-normal text-muted">Odds · market data · AI</span>
            </summary>
            <div className="px-4 pb-1">
              <DataProvidersPanel />
            </div>
          </details>

          {!hasSignals && apiStatusColor === "text-success" && (
            <section className="mb-4">
              <SectionHeader title="Start here" description="Run a scan from the bar above." />
              <div className="grid gap-3 sm:grid-cols-3">
                <PlaceholderCard
                  module="Stocks"
                  title="Stock swings"
                  description="Scan stock swings for RSI/MACD setups."
                />
                <PlaceholderCard
                  module="Options"
                  title="Options"
                  description="Deep scan for near-term premium moves."
                />
                <PlaceholderCard
                  module="Sports"
                  title="Sports +EV"
                  description="Scan sports odds, then build parlays."
                />
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
