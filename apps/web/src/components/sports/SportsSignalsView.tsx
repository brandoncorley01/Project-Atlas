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
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import type { SportsCategoryMeta } from "@/lib/sports-categories";
import {
  filterBySport,
  filterByWindow,
  filterSports,
  sortSports,
  type SportsFilterKey,
  type SportsSortKey,
  type SportsWindowKey,
} from "@/lib/sports-filters";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

interface SportsSignalsViewProps {
  initialItems: SportsSignal[];
  initialCategories?: SportsCategoryMeta[];
}

export function SportsSignalsView({
  initialItems,
  initialCategories = [],
}: SportsSignalsViewProps) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [categories, setCategories] = useState(initialCategories);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeSport, setActiveSport] = useState<string | null>(null);
  const [sort, setSort] = useState<SportsSortKey>("soonest");
  const [filter, setFilter] = useState<SportsFilterKey>("all");
  const [window, setWindow] = useState<SportsWindowKey>("week");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [parlaySelection, setParlaySelection] = useState<Set<string>>(new Set());
  const { status: oddsStatus, refresh: refreshOddsStatus } = useOddsApiStatus();

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
    let list = filterByWindow(items, window);
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
      const params = new URLSearchParams({ limit: "50", window });
      if (category) params.set("category", category);
      const res = await fetch(`${apiUrl}/signals/sports?${params}`, {
        headers: apiRequestHeaders(token),
      });
      if (res.ok) {
        const data = await res.json();
        setItems(data.items ?? []);
      }
    },
    [window],
  );

  async function handleWindowChange(next: SportsWindowKey) {
    setWindow(next);
    const token = await getToken();
    const apiUrl = getApiUrl();
    const params = new URLSearchParams({ limit: "50", window: next });
    if (activeCategory) params.set("category", activeCategory);
    const res = await fetch(`${apiUrl}/signals/sports?${params}`, {
      headers: apiRequestHeaders(token),
    });
    if (res.ok) {
      const data = await res.json();
      setItems(data.items ?? []);
    }
  }

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

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

  async function refreshSports(forceRefresh = false) {
    setLoading(true);
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(false);
      return;
    }

    const shouldForceLive = forceRefresh || cacheNeedsLive;
    const apiUrl = getApiUrl();
    const params = shouldForceLive ? "?force_refresh=true" : "";
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-sports${params}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
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
        setLoading(false);
        return;
      }

      const created = body.signals_created as number;
      const creditsUsed = body.credits_used as number | undefined;
      const cacheUsed = body.cache_used as boolean | undefined;
      const apiMessage = body.message as string | undefined;
      setMessage(
        apiMessage ??
          (created > 0
            ? `Found ${created} plays across active leagues · ${cacheUsed ? "0 credits (cached)" : `~${creditsUsed ?? "?"} credits`}`
            : "No edges met the threshold — try Fetch live odds for a fresh slate"),
      );

      await Promise.all([
        loadCategories(token),
        loadItems(token, activeCategory),
        refreshOddsStatus(),
      ]);
      router.refresh();
    } catch {
      setMessage("Backend not responding — run .\\scripts\\start-dev.ps1");
    }
    setLoading(false);
  }

  const activeMeta = categories.find((c) => c.slug === activeCategory);
  const cacheFresh = oddsStatus?.cache_fresh ?? false;
  const cacheNeedsLive = oddsStatus?.cache_needs_live_refresh ?? false;

  return (
    <div className="w-full min-w-0 overflow-x-clip">
      <SportsHeroBanner playCount={items.length} />

      <SportsStatsBar
        items={items}
        cacheFresh={cacheFresh}
        creditsRemaining={oddsStatus?.total_remaining}
      />

      <OddsQuotaBanner status={oddsStatus} />

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-muted">
          <p>
            <strong className="text-foreground">Step 1:</strong> Scan odds (this week) ·{" "}
            <strong className="text-foreground">Step 2:</strong> Tap <strong className="text-foreground">+</strong> to build a manual parlay or save bets ·{" "}
            <strong className="text-foreground">Step 3:</strong>{" "}
            <Link href="/parlays" className="font-semibold text-orange-400 hover:underline">
              Build parlays
            </Link>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => refreshSports(false)}
            disabled={loading}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-violet-600/25 disabled:opacity-50"
          >
            {loading
              ? "Scanning…"
              : cacheFresh
                ? "Rescore cached (0 credits)"
                : cacheNeedsLive
                  ? "Rescore narrow cache (0 credits)"
                  : "Scan sports odds"}
          </button>
          <button
            type="button"
            onClick={() => refreshSports(true)}
            disabled={loading}
            title="Uses API credits · scans in-season leagues first (MLB, WNBA, soccer, tennis) · skips far-future NFL lines in summer"
            className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
          >
            Fetch live odds
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
              ? "Try All leagues, All bet types, or scan for a fresh slate."
              : "Global leagues run 24/7 — scan sports odds or fetch live lines for NBA, NFL, MLB, NHL, soccer, and more."
          }
          action={
            <button
              type="button"
              onClick={() => refreshSports(false)}
              disabled={loading}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Scan sports odds
            </button>
          }
        />
      )}
    </div>
  );
}
