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
import { usesBffProxy } from "@/lib/api-url";
import { createClient } from "@/lib/supabase/client";
import type { Parlay } from "@/components/parlays/ParlayCard";
import { ParlayCard } from "@/components/parlays/ParlayCard";
import { StaleDataBanner } from "@/components/dashboard/StaleDataBanner";
import { API_START_HINT } from "@/lib/api-config";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { QuickStartGuide } from "@/components/ui/QuickStartGuide";
import { DashboardLegend } from "@/components/dashboard/DashboardLegend";
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
    warnings?: string[];
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

      const total =
        (dashboard.top_opportunities?.length ?? 0) +
        (dashboard.budget_opportunities?.length ?? 0) +
        (dashboard.stock_opportunities?.length ?? 0) +
        (dashboard.sports_opportunities?.length ?? 0);

      setApiStatus(
        total > 0
          ? `API connected · ${total} signals`
          : dashboard.meta?.warnings?.length
            ? `API connected · partial load (${dashboard.meta.warnings.length} warnings)`
            : "API connected · no signals yet",
      );
      setApiStatusColor("text-success");
      hasLoadedOnceRef.current = true;
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
      } else if (status === 404 || status === 502) {
        setApiStatus(
          err instanceof Error
            ? err.message
            : "Backend not configured — check NEXT_PUBLIC_API_URL on Vercel (must end with /api/v1)",
        );
      } else if (status === 503) {
        setApiStatus(err instanceof Error ? err.message : `Backend unreachable — ${API_START_HINT}`);
      } else if (status === 502) {
        setApiStatus("Database error — check Supabase connection");
      } else if (status === 500) {
        setApiStatus(err instanceof Error ? err.message : "API server error");
      } else if (err instanceof ApiError) {
        setApiStatus(err.message);
      } else {
        setApiStatus(`Cannot reach API — ${API_START_HINT}`);
      }
      setApiStatusColor("text-danger");
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
      const briefing = await apiFetch<AtlasBriefing>("/ai/briefing?refresh=true", token, {
        timeoutMs: 30_000,
      });
      setAtlasBriefing(briefing);
    } catch {
      // keep existing briefing on failure
    } finally {
      setBriefingRefreshing(false);
    }
  }, []);

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

  const statusVariant =
    loading
      ? "loading"
      : apiRestarting
        ? "warning"
        : apiStatusColor === "text-success"
          ? "success"
          : apiStatusColor === "text-danger"
            ? "danger"
            : "warning";

  return (
    <>
      <PageHeader
        title="Dashboard"
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
      <QuickStartGuide />

      <DashboardLegend />

      <StaleDataBanner meta={freshnessMeta ?? undefined} />

      <AtlasBriefingCard
        briefing={atlasBriefing}
        onRefresh={() => void refreshBriefing()}
        refreshing={briefingRefreshing}
      />

      <MarketIntelligenceCard intelligence={marketIntelligence} tracking={trackingStats} />

      {(performanceSummary?.total_logged ?? 0) > 0 || performanceSummary?.learning_active ? (
        <section className="mb-8 rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Pick performance (30 days)</h2>
              <p className="mt-1 text-sm text-muted">
                {performanceSummary?.win_rate_30d != null
                  ? `${performanceSummary.win_rate_30d}% win rate · ${performanceSummary.total_logged ?? 0} logged`
                  : `${performanceSummary?.total_logged ?? 0} outcomes logged`}
                {performanceSummary?.learning_active && " · Atlas is learning from your results"}
              </p>
              {performanceSummary?.learning_notes?.[0] && (
                <p className="mt-2 text-xs text-violet-200">{performanceSummary.learning_notes[0]}</p>
              )}
            </div>
            <Link
              href="/performance"
              className="rounded-lg border border-violet-500/40 px-3 py-1.5 text-sm font-medium text-violet-200 hover:bg-violet-500/10"
            >
              View learning →
            </Link>
          </div>
        </section>
      ) : (
        <section className="mb-8 rounded-xl border border-dashed border-border bg-surface/40 p-4 text-sm text-muted">
          After picks settle, tap <strong className="text-foreground">Win</strong> or{" "}
          <strong className="text-foreground">Loss</strong> on any card — or let Atlas auto-grade expired picks.
          Every scan is tracked automatically, even without watchlist.{" "}
          <Link href="/performance" className="text-accent hover:underline">
            Performance →
          </Link>
        </section>
      )}

      <section className="mb-8">
        <SectionHeader title="Breaking News" />
        <BreakingNewsStrip items={breakingNews} />
      </section>

      <DashboardSignals
        topOpportunities={topOpportunities}
        budgetOpportunities={budgetOpportunities}
        stockOpportunities={stockOpportunities}
        sportsOpportunities={sportsOpportunities}
      />

      {bestParlay && (
        <section className="mb-8">
          <SectionHeader title="Best Cross-Sport Parlay" href="/parlays" linkLabel="All parlays →" />
          <ParlayCard row={bestParlay} rank={1} />
        </section>
      )}

      <section className="mb-8">
        <SectionHeader
          title="Data Providers"
          description="Dial gauges show live provider health. The Odds API dial tracks pooled credits across all failover keys and updates after each scan."
        />
        <DataProvidersPanel />
      </section>

      {!hasSignals && apiStatusColor === "text-success" && (
        <section>
          <SectionHeader title="Quick Picks" description="Run a scan from the bar above to populate these modules." />
          <div className="grid gap-4 md:grid-cols-2">
            <PlaceholderCard
              module="Stocks"
              title="Best Stock Swing Setup"
              description='Use "Scan stock swings" in the scanner bar above to find ranked technical setups.'
            />
            <PlaceholderCard
              module="Sports"
              title="Best Sports +EV Play"
              description='Add ODDS_API_KEY and use "Scan sports odds" in the scanner bar for ranked lines.'
            />
            <PlaceholderCard
              module="Options"
              title="Best Retail Options Setup"
              description='Use "Deep scan market" above to find ranked options opportunities.'
            />
          </div>
        </section>
      )}
        </>
      )}
    </>
  );
}
