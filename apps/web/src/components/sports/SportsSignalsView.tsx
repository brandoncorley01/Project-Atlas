"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SportsSignalCard, type SportsSignal } from "@/components/sports/SportsSignalCard";
import { ManualParlayBuilder } from "@/components/sports/ManualParlayBuilder";
import { SportsCategoryTabs } from "@/components/sports/SportsCategoryTabs";
import { SportFilterTabs } from "@/components/sports/SportFilterTabs";
import { SportsToolbar } from "@/components/sports/SportsToolbar";
import { SportsHeroBanner, SportsStatsBar } from "@/components/sports/SportsStatsBar";
import { OddsQuotaBanner, useOddsApiStatus } from "@/components/sports/OddsQuotaBanner";
import { SportsEventSearch } from "@/components/sports/SportsEventSearch";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import type { SportsCategoryMeta } from "@/lib/sports-categories";
import {
  dedupeOneSidePerMarket,
  filterBySport,
  filterByWindow,
  filterSports,
  sortSports,
  type SportsFilterKey,
  type SportsSortKey,
  type SportsWindowKey,
} from "@/lib/sports-filters";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { fetchIntelligenceStatus } from "@/lib/sports-intelligence-api";

interface SportsSignalsViewProps {
  initialItems: SportsSignal[];
  initialCategories?: SportsCategoryMeta[];
}

export function SportsSignalsView({
  initialItems,
  initialCategories = [],
}: SportsSignalsViewProps) {
  const router = useRouter();
  const [items, setItems] = useState(() => dedupeOneSidePerMarket(initialItems));
  const [categories, setCategories] = useState(initialCategories);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeSport, setActiveSport] = useState<string | null>(null);
  const [sort, setSort] = useState<SportsSortKey>("soonest");
  const [filter, setFilter] = useState<SportsFilterKey>("all");
  const [window, setWindow] = useState<SportsWindowKey>("month");
  const [loading, setLoading] = useState<null | "scan" | "live" | "rescore" | "openai">(null);
  const [message, setMessage] = useState<string | null>(null);
  const [parlaySelection, setParlaySelection] = useState<Set<string>>(new Set());
  const [intelligenceEnabled, setIntelligenceEnabled] = useState(false);
  const { status: oddsStatus, refresh: refreshOddsStatus } = useOddsApiStatus();

  useEffect(() => {
    void fetchIntelligenceStatus().then((s) => setIntelligenceEnabled(s.enabled));
  }, []);

  function toggleParlayLeg(id: string) {
    setParlaySelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 6) {
        next.add(id);
      }
      return next;
    });
  }

  function clearParlaySelection() {
    setParlaySelection(new Set());
  }

  const displayedItems = useMemo(() => {
    let list = dedupeOneSidePerMarket(items);
    list = filterByWindow(list, window);
    list = filterBySport(list, activeSport);
    list = filterSports(list, filter);
    return sortSports(list, sort);
  }, [items, activeSport, filter, sort, window]);

  const loadCategories = useCallback(async (token?: string) => {
    const apiUrl = getApiUrl();
    const res = await fetch(`${apiUrl}/signals/sports/categories`, {
      headers: apiRequestHeaders(token),
    });
    if (res.ok) {
      const data = await res.json();
      setCategories(data.categories ?? []);
    }
  }, []);

  const loadItems = useCallback(
    async (token?: string, category?: string | null) => {
      const apiUrl = getApiUrl();
      const params = new URLSearchParams({ limit: "100", window });
      if (category) params.set("category", category);
      const res = await fetch(`${apiUrl}/signals/sports?${params}`, {
        headers: apiRequestHeaders(token),
        cache: "no-store",
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      if (res.ok) {
        const data = await res.json();
        setItems(dedupeOneSidePerMarket(data.items ?? []));
      }
    },
    [window],
  );

  async function handleWindowChange(next: SportsWindowKey) {
    setWindow(next);
    const token = await getToken();
    const apiUrl = getApiUrl();
    const params = new URLSearchParams({ limit: "100", window: next });
    if (activeCategory) params.set("category", activeCategory);
    const res = await fetch(`${apiUrl}/signals/sports?${params}`, {
      headers: apiRequestHeaders(token),
    });
    if (res.ok) {
      const data = await res.json();
      setItems(dedupeOneSidePerMarket(data.items ?? []));
    }
  }

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  useEffect(() => {
    void (async () => {
      const token = await getToken();
      if (token || usesBffProxy()) {
        await loadItems(token, activeCategory);
      }
    })();
    // Refresh on mount so picks persist after API changes without a full reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (initialCategories.length) return;
    void (async () => {
      const token = await getToken();
      if (token || usesBffProxy()) await loadCategories(token);
    })();
  }, [initialCategories.length, loadCategories]);

  async function handleCategoryChange(slug: string | null) {
    setActiveCategory(slug);
    setActiveSport(null);
    const token = await getToken();
    await loadItems(token, slug);
  }

  async function refreshSports(mode: "scan" | "live" | "rescore") {
    setLoading(mode);
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(null);
      return;
    }

    const apiUrl = getApiUrl();
    const params = new URLSearchParams();
    if (mode === "live") params.set("force_refresh", "true");
    if (mode === "rescore") params.set("cache_only", "true");
    const query = params.toString() ? `?${params}` : "";
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-sports${query}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        signal: AbortSignal.timeout(300000),
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = typeof body.detail === "string" ? body.detail : "Scan failed";
        setMessage(
          res.status === 404
            ? "Sports scan endpoint not found — restart API with .\\scripts\\start-dev.ps1"
            : detail,
        );
        setLoading(null);
        return;
      }

      const created = body.signals_created as number;
      const kept = body.signals_kept as boolean | undefined;
      const creditsUsed = body.credits_used as number | undefined;
      const cacheUsed = body.cache_used as boolean | undefined;
      const apiMessage = body.message as string | undefined;
      setMessage(
        apiMessage ??
          (kept
            ? "No new edges found — kept your current picks on the board"
            : created > 0
              ? `Found ${created} plays · ${cacheUsed ? "0 Odds credits (cached)" : `~${creditsUsed ?? "?"} Odds credits`}`
              : "No edges met the threshold — try Fetch live odds or OpenAI"),
      );

      await Promise.all([
        loadCategories(token),
        loadItems(token, activeCategory),
        refreshOddsStatus(),
      ]);
      router.refresh();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
    } catch {
      setMessage("Backend not responding — run .\\scripts\\start-dev.ps1");
    }
    setLoading(null);
  }

  async function refreshOpenAiPicks() {
    setLoading("openai");
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(null);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-sports-openai`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        signal: AbortSignal.timeout(300000),
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = typeof body.detail === "string" ? body.detail : "OpenAI scan failed";
        setMessage(
          res.status === 404
            ? "OpenAI sports endpoint not found — redeploy/restart the API"
            : detail,
        );
        setLoading(null);
        return;
      }
      setMessage(
        (body.message as string | undefined) ??
          `OpenAI web desk added ${body.signals_created ?? 0} analyst/popular-bettor picks (0 Odds credits)`,
      );
      await Promise.all([
        loadCategories(token),
        loadItems(token, activeCategory),
        refreshOddsStatus(),
      ]);
      router.refresh();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
    } catch {
      setMessage("Backend not responding — run .\\scripts\\start-dev.ps1");
    }
    setLoading(null);
  }

  const activeMeta = categories.find((c) => c.slug === activeCategory);
  const cacheRescoreFree = oddsStatus?.cache_rescore_free ?? false;
  const cacheFresh = oddsStatus?.cache_fresh ?? false;
  const cacheNeedsLive = oddsStatus?.cache_needs_live_refresh ?? false;
  const busy = loading !== null;

  return (
    <div className="w-full min-w-0 overflow-x-clip">
      <SportsHeroBanner playCount={items.length} />

      <SportsStatsBar
        items={items}
        cacheRescoreFree={cacheRescoreFree}
        cacheFresh={cacheFresh}
        cacheNeedsLive={cacheNeedsLive}
        creditsRemaining={oddsStatus?.total_remaining}
        keyCount={oddsStatus?.key_count}
      />

      <OddsQuotaBanner status={oddsStatus} />

      <SportsEventSearch
        onBetLogged={async () => {
          const token = await getToken();
          await Promise.all([loadCategories(token), loadItems(token, activeCategory)]);
          router.refresh();
        }}
      />

      {intelligenceEnabled && (
        <div className="mb-4 rounded-xl border border-violet-500/30 bg-violet-500/10 px-4 py-3 text-sm text-violet-100">
          <strong className="text-violet-200">Atlas Intelligence</strong> is active — open any pick
          for expert consensus, news context, and confidence adjustments.
        </div>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="text-sm text-muted">
          <p>
            <strong className="text-foreground">Odds API:</strong> Scan / Fetch / Rescore ·{" "}
            <strong className="text-foreground">OpenAI:</strong> web analyst consensus (0 Odds credits) ·{" "}
            Tap <strong className="text-foreground">+</strong> for parlays ·{" "}
            <Link href="/parlays" className="font-semibold text-orange-400 hover:underline">
              Build parlays
            </Link>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => refreshSports("scan")}
            disabled={busy}
            title="Scan sports odds — uses warm cache when available, otherwise a live pull."
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-violet-600/25 disabled:opacity-50"
          >
            {loading === "scan" ? "Scanning…" : "Scan sports odds"}
          </button>
          <button
            type="button"
            onClick={() => refreshSports("live")}
            disabled={busy}
            title="Fetch live FanDuel/DraftKings lines for US-core leagues (~4 Odds API credits)."
            className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
          >
            {loading === "live" ? "Fetching…" : "Fetch live odds"}
          </button>
          <button
            type="button"
            onClick={() => refreshSports("rescore")}
            disabled={busy}
            title="Rescore cached odds only — 0 Odds API credits. Seed cache with Fetch live odds first."
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {loading === "rescore" ? "Rescoring…" : "Rescore (0 credits)"}
          </button>
          <button
            type="button"
            onClick={() => refreshOpenAiPicks()}
            disabled={busy}
            title="OpenAI browses the public web for analyst and popular-bettor picks. Uses OPENAI_API_KEY only — 0 Odds API credits."
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
          >
            {loading === "openai" ? "OpenAI searching…" : "OpenAI web picks"}
          </button>
        </div>
      </div>

      <SportsCategoryTabs
        categories={categories}
        activeSlug={activeCategory}
        onSelect={handleCategoryChange}
      />

      <SportFilterTabs
        items={items}
        activeSport={activeSport}
        onSelect={setActiveSport}
        extraLeagues={oddsStatus?.league_catalog ?? oddsStatus?.near_term_leagues ?? []}
      />

      <SportsToolbar
        sort={sort}
        filter={filter}
        window={window}
        onSortChange={setSort}
        onFilterChange={setFilter}
        onWindowChange={handleWindowChange}
        resultCount={displayedItems.length}
      />

      {activeMeta && (
        <div className="mb-4 rounded-xl border border-violet-500/25 bg-violet-500/8 px-4 py-3">
          <p className="text-sm font-semibold text-violet-200">{activeMeta.title}</p>
          <p className="mt-1 text-sm text-muted">{activeMeta.description}</p>
          <Link
            href={`/sports/category/${activeMeta.slug}`}
            className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
          >
            Read full category guide →
          </Link>
        </div>
      )}

      {message && (
        <p className="mb-4 rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-muted">
          {message}
        </p>
      )}

      <ManualParlayBuilder
        signals={displayedItems}
        selectedIds={parlaySelection}
        onToggle={toggleParlayLeg}
        onClear={clearParlaySelection}
      />

      {loading && items.length === 0 ? (
        <ListSkeleton count={3} />
      ) : displayedItems.length > 0 ? (
        <div className="sports-signals-list space-y-4">
          {displayedItems.map((item, index) => (
            <SportsSignalCard
              key={item.id}
              row={item}
              rank={index + 1}
              parlaySelected={parlaySelection.has(item.id)}
              onParlayToggle={toggleParlayLeg}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={activeCategory || activeSport || filter !== "all" ? "No plays match these filters" : "No upcoming sports plays"}
          description={
            activeCategory || activeSport || filter !== "all"
              ? "Try All leagues, set Window to Today for same-day parlays, or widen (Next 48h / Next 30 days), then scan."
              : "Use Fetch live odds for FanDuel/DraftKings lines, Rescore for free re-ranks, or OpenAI web picks for analyst consensus."
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => refreshSports("scan")}
                disabled={busy}
                className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {loading === "scan" ? "Scanning…" : "Scan sports odds"}
              </button>
              <button
                type="button"
                onClick={() => refreshOpenAiPicks()}
                disabled={busy}
                className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 disabled:opacity-50"
              >
                {loading === "openai" ? "OpenAI searching…" : "OpenAI web picks"}
              </button>
            </div>
          }
        />
      )}
    </div>
  );
}
