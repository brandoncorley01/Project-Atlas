"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  isUserSportsPick,
  sortSports,
  type SportsFilterKey,
  type SportsSortKey,
  type SportsWindowKey,
} from "@/lib/sports-filters";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { fetchIntelligenceStatus } from "@/lib/sports-intelligence-api";
import {
  boardAsOfFromItems,
  hydrateSportsItems,
  markSportsBoardAction,
  readSportsBoardCache,
  writeSportsBoardCache,
} from "@/lib/sports-board-cache";

interface SportsSignalsViewProps {
  initialItems: SportsSignal[];
  initialCategories?: SportsCategoryMeta[];
}

interface SportsListMeta {
  board_as_of?: string | null;
  odds_fetched_at?: string | null;
  odds_age_minutes?: number | null;
}

export function SportsSignalsView({
  initialItems,
  initialCategories = [],
}: SportsSignalsViewProps) {
  const router = useRouter();
  const [items, setItems] = useState(() => hydrateSportsItems(initialItems));
  const [categories, setCategories] = useState(initialCategories);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeSport, setActiveSport] = useState<string | null>(null);
  const [sort, setSort] = useState<SportsSortKey>("soonest");
  const [filter, setFilter] = useState<SportsFilterKey>("all");
  const [window, setWindow] = useState<SportsWindowKey>(
    () => readSportsBoardCache()?.window ?? "today",
  );
  const [loading, setLoading] = useState<
    null | "scan" | "live" | "rescore" | "openai" | "repair"
  >(null);
  const [message, setMessage] = useState<string | null>(null);
  const [parlaySelection, setParlaySelection] = useState<Set<string>>(new Set());
  const [intelligenceEnabled, setIntelligenceEnabled] = useState(false);
  const [boardAsOf, setBoardAsOf] = useState<string | null>(
    () => readSportsBoardCache()?.boardAsOf ?? boardAsOfFromItems(initialItems),
  );
  const [lastActionAt, setLastActionAt] = useState<string | null>(
    () => readSportsBoardCache()?.lastActionAt ?? null,
  );
  const [lastActionKind, setLastActionKind] = useState<
    "scan" | "live" | "rescore" | "openai" | "repair" | null
  >(() => readSportsBoardCache()?.lastActionKind ?? null);
  const [oddsFetchedAt, setOddsFetchedAt] = useState<string | null>(
    () => readSportsBoardCache()?.oddsFetchedAt ?? null,
  );
  const { status: oddsStatus, refresh: refreshOddsStatus } = useOddsApiStatus();
  const insightFetchFallbackUsed = useRef(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const fetchBlocked = Boolean(
    oddsStatus?.quota_exhausted || oddsStatus?.live_fetch_allowed === false,
  );

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
    // League filter is applied server-side when activeSport is set; keep a client
    // pass so counts stay consistent if the API payload is wider than the tab.
    list = filterBySport(list, activeSport);
    // Insight / Props categories already define membership — don't let a leftover
    // bet-type filter wipe the board.
    if (activeCategory !== "atlas_insight" && activeCategory !== "player_props") {
      list = filterSports(list, filter);
    }
    return sortSports(list, sort);
  }, [items, activeCategory, activeSport, filter, sort, window]);

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

  const attachKalshiPulse = useCallback(async (rows: SportsSignal[]) => {
    if (!rows.length) return rows;
    const needs = rows.filter((r) => !r.public_market && !r.scoring_snapshot?.public_market);
    if (!needs.length) return rows;
    try {
      const res = await fetch("/api/kalshi/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        cache: "no-store",
        body: JSON.stringify({ items: needs.slice(0, 60) }),
      });
      if (!res.ok) return rows;
      const data = (await res.json()) as { items?: SportsSignal[] };
      const enriched = data.items ?? [];
      if (!enriched.length) return rows;
      const byId = new Map(
        enriched
          .filter((r) => r.public_market)
          .map((r) => [r.id, r.public_market] as const),
      );
      if (!byId.size) return rows;
      return rows.map((row) => {
        const pulse = byId.get(row.id);
        return pulse ? { ...row, public_market: pulse } : row;
      });
    } catch {
      return rows;
    }
  }, []);

  const applyBoard = useCallback(
    (
      next: SportsSignal[],
      meta?: SportsListMeta | null,
      opts?: { replaceEmpty?: boolean; preserveUserBets?: boolean },
    ) => {
      const replaceEmpty = opts?.replaceEmpty ?? false;
      const preserveUserBets = opts?.preserveUserBets ?? !replaceEmpty;
      const prev = itemsRef.current;
      let board = dedupeOneSidePerMarket(next);
      if (board.length === 0 && prev.length > 0 && !replaceEmpty) {
        if (meta?.odds_fetched_at) {
          setOddsFetchedAt(meta.odds_fetched_at);
          writeSportsBoardCache(readSportsBoardCache()?.items ?? [], {
            oddsFetchedAt: meta.odds_fetched_at,
          });
        }
        return;
      }
      if (preserveUserBets && prev.length > 0) {
        const boardIds = new Set(board.map((i) => i.id).filter(Boolean));
        const missingUser = prev.filter(
          (i) => isUserSportsPick(i) && i.id && !boardIds.has(i.id),
        );
        if (missingUser.length) {
          board = dedupeOneSidePerMarket([...missingUser, ...board]);
        }
      }
      setItems(board);
      const asOf = meta?.board_as_of ?? boardAsOfFromItems(board);
      if (asOf) setBoardAsOf(asOf);
      if (meta?.odds_fetched_at) setOddsFetchedAt(meta.odds_fetched_at);
      writeSportsBoardCache(board, {
        boardAsOf: asOf,
        oddsFetchedAt: meta?.odds_fetched_at ?? undefined,
      });
    },
    [],
  );

  const upsertLoggedBet = useCallback((item: SportsSignal) => {
    setItems((prev) => {
      const without = prev.filter((r) => r.id !== item.id);
      const next = dedupeOneSidePerMarket([item, ...without]);
      writeSportsBoardCache(next, {
        boardAsOf: boardAsOfFromItems(next) ?? undefined,
      });
      return next;
    });
  }, []);

  const loadItems = useCallback(
    async (
      token?: string,
      category?: string | null,
      sport?: string | null,
      opts?: { replaceEmpty?: boolean },
    ): Promise<SportsSignal[]> => {
      const apiUrl = getApiUrl();
      // Always fetch the full upcoming slate — Window/Sort/Bet type filter client-side.
      // Fetching a narrow window then switching to a wider one used to leave the board stuck.
      const params = new URLSearchParams({ limit: "200", window: "all" });
      if (category) params.set("category", category);
      if (sport) params.set("sport", sport);
      try {
        const res = await fetch(`${apiUrl}/signals/sports?${params}`, {
          headers: apiRequestHeaders(token),
          cache: "no-store",
          credentials: usesBffProxy() ? "include" : "same-origin",
        });
        if (!res.ok) return itemsRef.current;
        const data = (await res.json()) as {
          items?: SportsSignal[];
          meta?: SportsListMeta;
        };
        const base = dedupeOneSidePerMarket(data.items ?? []);
        applyBoard(base, data.meta, { replaceEmpty: opts?.replaceEmpty });
        // Second pass: guarantee Kalshi pulse even if upstream API has no enrichment.
        const withKalshi = await attachKalshiPulse(base);
        if (withKalshi !== base) {
          applyBoard(withKalshi, data.meta, { replaceEmpty: opts?.replaceEmpty });
          itemsRef.current = withKalshi;
          return withKalshi;
        }
        itemsRef.current = base;
        return base;
      } catch {
        // Keep existing / cached board on network errors.
        return itemsRef.current;
      }
    },
    [attachKalshiPulse, applyBoard],
  );

  async function handleWindowChange(next: SportsWindowKey) {
    // Client-side only — items already hold the full slate from window=all fetches.
    setWindow(next);
    writeSportsBoardCache(itemsRef.current, { window: next });
  }

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  useEffect(() => {
    // Soft remount: show cached/SSR board immediately; refresh without clearing on empty.
    // Do NOT await resolve-outcomes here — that was wiping the board on every navigation.
    void (async () => {
      const token = await getToken();
      if (!(token || usesBffProxy())) return;
      try {
        await fetch(`${getApiUrl()}/signals/sports/user-bets/recover`, {
          method: "POST",
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
        });
      } catch {
        // Recovery is best-effort — still refresh the board.
      }
      await loadItems(token, activeCategory, activeSport, { replaceEmpty: false });
      void refreshOddsStatus();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const fetched = oddsStatus?.cache_fetched_at;
    if (!fetched) return;
    setOddsFetchedAt(fetched);
    writeSportsBoardCache(readSportsBoardCache()?.items ?? [], { oddsFetchedAt: fetched });
  }, [oddsStatus?.cache_fetched_at]);

  function rememberAction(kind: "scan" | "live" | "rescore" | "openai" | "repair") {
    const at = new Date().toISOString();
    setLastActionAt(at);
    setLastActionKind(kind);
    markSportsBoardAction(kind);
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
    // Keep bet-type filter aligned so Insight/Props category isn't double-filtered away.
    if (slug === "atlas_insight") {
      setFilter("openai");
      setSort("openai");
    } else if (slug === "player_props") {
      setFilter("player_props");
      setSort("player_props");
    } else {
      // Edge metrics should not hide Insight via a leftover bet-type filter.
      setFilter("all");
    }
    const token = await getToken();
    // Category/sport changes are intentional filters — allow empty results.
    await loadItems(token, slug, null, { replaceEmpty: true });
  }

  async function handleSportChange(sport: string | null) {
    setActiveSport(sport);
    const token = await getToken();
    await loadItems(token, activeCategory, sport, { replaceEmpty: true });
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
    // Scan + Rescore are always cache-only (0 Odds credits).
    // Only Fetch live odds spends credits — never auto-seed from Scan.
    if (mode === "scan" || mode === "rescore") {
      params.set("cache_only", "true");
    }
    const query = params.toString() ? `?${params}` : "";
    try {
      if (mode === "live") {
        const estimate = oddsStatus?.estimated_live_scan_credits ?? 8;
        const remaining = oddsStatus?.total_remaining;
        const ok = globalThis.confirm(
          `Fetch live odds spends ~${estimate} Odds API credits` +
            (remaining != null ? ` (${remaining} left)` : "") +
            ".\n\nOnly tap this when the cache is empty or missing leagues. " +
            "Scan and Rescore are free.\n\nContinue?",
        );
        if (!ok) {
          setLoading(null);
          return;
        }
      }
      const res = await fetch(`${apiUrl}/engine/refresh-sports${query}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        signal: AbortSignal.timeout(180000),
      });
      let body: Record<string, unknown> = {};
      try {
        body = await res.json();
      } catch {
        setMessage(
          res.status === 503
            ? "Sports scan timed out — try Rescore (0 credits) or Fetch live odds."
            : `Sports scan failed (HTTP ${res.status}). Try again in a moment.`,
        );
        setLoading(null);
        return;
      }
      if (!res.ok || body.ok === false || body.status === "error") {
        const detail =
          (typeof body.message === "string" && body.message) ||
          (typeof body.detail === "string" && body.detail) ||
          "Scan failed";
        setMessage(
          res.status === 404
            ? "Sports scan endpoint not found — restart API with .\\scripts\\start-dev.ps1"
            : res.status === 503
              ? detail || "API timed out — try Rescore or restart the API."
              : detail,
        );
        setLoading(null);
        return;
      }

      const created = Number(body.signals_created ?? 0);
      const kept = body.signals_kept as boolean | undefined;
      const creditsUsed = body.credits_used as number | undefined;
      const cacheUsed = body.cache_used as boolean | undefined;
      const liveOddsPulled = Boolean(body.live_odds_pulled || body.insight_pending);
      const apiMessage = body.message as string | undefined;
      rememberAction(mode);
      setMessage(
        apiMessage ??
          (kept
            ? "No new edges found — kept your current picks on the board"
            : created > 0
              ? `Found ${created} plays · ${cacheUsed ? "0 Odds credits (cached)" : `~${creditsUsed ?? "?"} Odds credits`}`
              : "No edges met the threshold — try Rescore (0 credits). Fetch only if the cache is empty."),
      );

      setFilter("all");
      setSort("opportunity");
      setActiveCategory(null);
      setActiveSport(null);

      await loadItems(token, null, null, {
        replaceEmpty: created > 0,
      });
      await Promise.all([loadCategories(token), refreshOddsStatus()]);
      // Stay on Today — auto-widening to Next 48h hid tonight's empty slate after Scan/Fetch.
      setWindow("today");
      writeSportsBoardCache(itemsRef.current, { window: "today" });
      const todayN = filterByWindow(itemsRef.current, "today").length;
      const soonN = filterByWindow(itemsRef.current, "soon").length;
      const todayStillEmpty = Boolean(body.today_still_empty) || todayN === 0;
      if (todayStillEmpty && soonN > 0) {
        setMessage(
          (apiMessage ? `${apiMessage} · ` : "") +
            `Today (next 24h) is empty — ${soonN} play${soonN === 1 ? "" : "s"} in Next 48h. ` +
            "Tap Show Next 48h below, or Repair sports board for tonight's live odds.",
        );
      } else if (todayStillEmpty && created > 0) {
        setMessage(
          (apiMessage ? `${apiMessage} · ` : "") +
            "Today (next 24h) is still empty — tap Repair sports board to Fetch tonight's odds.",
        );
      }
      router.refresh();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));

      // Separate request after live odds — avoids one long Fetch+Insight call that 503s the BFF.
      // Only chain Insight when Scan/Fetch actually saved plays; otherwise Insight has nothing
      // to rank and quietPrefix would block the Fetch-live fallback.
      if (liveOddsPulled && created > 0) {
        setLoading(null);
        await refreshOpenAiPicks({ quietPrefix: apiMessage, preferWindow: "today" });
        return;
      }
      if (liveOddsPulled && created <= 0) {
        setMessage(
          apiMessage
            ? `${apiMessage} · Board still empty — tap Repair sports board or Rescore (0 credits).`
            : "Live odds pulled but no plays ranked — tap Repair sports board.",
        );
      }
    } catch (err) {
      const timedOut =
        err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError");
      setMessage(
        timedOut
          ? "Sports scan timed out — try Rescore (0 credits) or Fetch live odds."
          : "Backend not responding — run .\\scripts\\start-dev.ps1",
      );
    }
    setLoading(null);
  }

  async function repairSportsBoard() {
    setLoading("repair");
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(null);
      return;
    }

    const estimate = oddsStatus?.estimated_live_scan_credits ?? 8;
    const remaining = oddsStatus?.total_remaining;
    const ok = globalThis.confirm(
      `Repair will Fetch live odds once (~${estimate} credits` +
        (remaining != null ? `, ${remaining} left` : "") +
        ") for Today's slate (next 24 hours).\n\n" +
        "Scan and Rescore stay free after that.\n\nContinue?",
    );
    if (!ok) {
      setLoading(null);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/repair-sports`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        signal: AbortSignal.timeout(180000),
      });
      let body: Record<string, unknown> = {};
      try {
        body = await res.json();
      } catch {
        setMessage(
          res.status === 503
            ? "Repair timed out — try again, or tap Fetch live odds once."
            : `Repair failed (HTTP ${res.status}). Try again in a moment.`,
        );
        setLoading(null);
        return;
      }
      if (!res.ok || body.ok === false || body.status === "error") {
        const detail =
          (typeof body.message === "string" && body.message) ||
          (typeof body.error === "string" && body.error) ||
          (typeof body.detail === "string" && body.detail) ||
          "Repair failed";
        setMessage(detail);
        // Always reload after Repair — ok:false used to skip loadItems and leave a blank
        // board even when rows were written (empty PostgREST representation) or when a
        // warm-cache fallback saved picks under a soft error.
        const createdOnError = Number(body.signals_created ?? 0);
        setFilter("all");
        setSort("opportunity");
        setActiveCategory(null);
        setActiveSport(null);
        await loadItems(token, null, null, { replaceEmpty: createdOnError > 0 });
        await Promise.all([loadCategories(token), refreshOddsStatus()]);
        setWindow("today");
        writeSportsBoardCache(itemsRef.current, { window: "today" });
        const todayN = filterByWindow(itemsRef.current, "today").length;
        const soonN = filterByWindow(itemsRef.current, "soon").length;
        if (todayN === 0 && soonN > 0) {
          setMessage(
            `${detail} · ${soonN} play${soonN === 1 ? "" : "s"} in Next 48h — tap Show Next 48h.`,
          );
        }
        rememberAction("repair");
        router.refresh();
        globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
        setLoading(null);
        return;
      }

      const created = Number(body.signals_created ?? 0);
      const apiMessage = body.message as string | undefined;
      rememberAction("repair");
      setMessage(
        apiMessage ??
          (created > 0
            ? `Repaired — ${created} plays on the board`
            : "Repair finished — board still empty"),
      );

      setFilter("all");
      setSort("opportunity");
      setActiveCategory(null);
      setActiveSport(null);

      await loadItems(token, null, null, {
        replaceEmpty: created > 0,
      });
      await Promise.all([loadCategories(token), refreshOddsStatus()]);
      // Repair must stay on Today even when the slate is still empty. Auto-widening
      // to Next 48h hid a failed Today fill and looked like Repair "didn't pull today's odds."
      setWindow("today");
      writeSportsBoardCache(itemsRef.current, { window: "today" });
      const todayN = filterByWindow(itemsRef.current, "today").length;
      const soonN = filterByWindow(itemsRef.current, "soon").length;
      const todayStillEmpty = Boolean(body.today_still_empty) || todayN === 0;
      if (todayStillEmpty && soonN > 0) {
        setMessage(
          (apiMessage ? `${apiMessage} · ` : "") +
            `Today is still empty — ${soonN} play${soonN === 1 ? "" : "s"} in Next 48h. ` +
            "Tap Show Next 48h, or Repair again for tonight.",
        );
      } else if (todayStillEmpty) {
        setMessage(
          apiMessage ??
            "Repair finished but Today is still empty — check Odds credits, then Repair again.",
        );
      }
      router.refresh();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));

      // Don't chain Insight here — it used to flip the Window off Today. Repair is odds-only.
    } catch (err) {
      const timedOut =
        err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError");
      setMessage(
        timedOut
          ? "Repair timed out — try again, or tap Fetch live odds once."
          : "Backend not responding — run .\\scripts\\start-dev.ps1",
      );
    }
    setLoading(null);
  }

  async function refreshOpenAiPicks(opts?: {
    quietPrefix?: string | null;
    /** When true, skip auto-Fetch fallback (prevents Fetch→Insight→Fetch loops). */
    skipFetchFallback?: boolean;
    /** Keep this window after Insight (Repair stays on Today instead of flipping away). */
    preferWindow?: SportsWindowKey;
  }) {
    setLoading("openai");
    if (!opts?.quietPrefix) setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(null);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-sports-openai?fast=true&limit=12`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        signal: AbortSignal.timeout(120000),
      });
      let body: Record<string, unknown> = {};
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        body = {};
      }
      if (!res.ok) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : res.status === 503
              ? "Atlas Insight timed out — the API is slow or unreachable. Tap Restart, then try again."
              : "Atlas Insight scan failed";
        setMessage(
          res.status === 404
            ? "Atlas Insight endpoint not found — redeploy/restart the API"
            : detail,
        );
        setLoading(null);
        return;
      }
      const created = Number(body.signals_created ?? 0);
      const failed = body.status === "error" || body.ok === false;
      const apiMessage =
        typeof body.message === "string" ? body.message : undefined;
      const needsLiveOdds = Boolean(body.needs_live_odds) ||
        Boolean(
          failed &&
            apiMessage &&
            /fetch live odds|no fanduel|no.*markets available|cache/i.test(apiMessage),
        );
      const combined =
        opts?.quietPrefix && apiMessage
          ? `${opts.quietPrefix} · ${apiMessage}`
          : apiMessage;

      // Cold odds cache on a direct Insight tap: seed with Fetch, then Insight re-runs.
      // Skip when we already arrived here from Fetch (quietPrefix) to avoid a loop.
      if (
        (failed || created <= 0) &&
        needsLiveOdds &&
        !opts?.skipFetchFallback &&
        !opts?.quietPrefix &&
        !insightFetchFallbackUsed.current &&
        !fetchBlocked
      ) {
        insightFetchFallbackUsed.current = true;
        setMessage(
          "No FanDuel markets in cache — fetching live odds, then Atlas Insight will rank…",
        );
        setLoading(null);
        await refreshSports("live");
        return;
      }

      setMessage(
        combined ??
          (failed
            ? "Atlas Insight failed — try again"
            : `Atlas Insight added ${created} picks`),
      );
      if (failed || created <= 0) {
        // Stay on the current board — don't flip to an empty Insight filter.
        await refreshOddsStatus();
        setLoading(null);
        return;
      }
      insightFetchFallbackUsed.current = false;
      rememberAction("openai");
      // Keep the full board visible, but float Insight picks to the top so the run is obvious.
      // Repair callers pin Today — don't yank the window out to All dates / 48h after Insight.
      setWindow(opts?.preferWindow ?? "today");
      setFilter("all");
      setSort("openai");
      setActiveSport(null);
      setActiveCategory(null);
      await Promise.all([
        loadCategories(token),
        loadItems(token, null, null, { replaceEmpty: true }),
        refreshOddsStatus(),
      ]);
      router.refresh();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setMessage(
        msg.includes("timeout") || msg.includes("Timeout") || msg.includes("aborted")
          ? "Atlas Insight timed out — restart the API, then try again."
          : "Backend not responding — run .\\scripts\\start-dev.ps1",
      );
    }
    setLoading(null);
  }

  const activeMeta = categories.find((c) => c.slug === activeCategory);
  const cacheRescoreFree = oddsStatus?.cache_rescore_free ?? false;
  const cacheFresh = oddsStatus?.cache_fresh ?? false;
  const cacheNeedsLive = oddsStatus?.cache_needs_live_refresh ?? false;
  const busy = loading !== null;
  const showRepair =
    items.length === 0 ||
    Boolean(oddsStatus?.missing_today_slate) ||
    (oddsStatus != null &&
      oddsStatus.cache_has_data === false &&
      (oddsStatus.today_event_count ?? 0) === 0);

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
        oddsFetchedAt={oddsFetchedAt ?? oddsStatus?.cache_fetched_at}
        oddsAgeMinutes={oddsStatus?.cache_age_minutes}
        boardAsOf={boardAsOf}
        lastActionAt={lastActionAt}
        lastActionKind={lastActionKind}
      />

      <OddsQuotaBanner status={oddsStatus} />

      <SportsEventSearch
        onBetLogged={async (item) => {
          if (item?.id) upsertLoggedBet(item);
          const token = await getToken();
          await Promise.all([
            loadCategories(token),
            loadItems(token, activeCategory, activeSport, { replaceEmpty: false }),
          ]);
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
            <strong className="text-foreground">Atlas Insight:</strong> FanDuel-verified props & lines ·{" "}
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
            title="Scan sports odds from cache only — 0 Odds credits. Never spends. Use Fetch only when the cache is empty."
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-violet-600/25 disabled:opacity-50"
          >
            {loading === "scan" ? "Scanning…" : "Scan sports odds"}
          </button>
          {showRepair && (
            <button
              type="button"
              onClick={() => void repairSportsBoard()}
              disabled={busy || fetchBlocked}
              title={
                fetchBlocked
                  ? "Odds credits exhausted — add a new free Odds API key, then Repair again."
                  : "Recover missing picks: warm durable cache rescans free; cold cache does one live Fetch."
              }
              className="rounded-lg border border-amber-500/50 bg-amber-500/15 px-4 py-2 text-sm font-semibold text-amber-100 hover:bg-amber-500/25 disabled:opacity-50"
            >
              {loading === "repair" ? "Repairing…" : "Repair sports board"}
            </button>
          )}
          <button
            type="button"
            onClick={() => refreshSports("live")}
            disabled={busy || fetchBlocked}
            title={
              fetchBlocked
                ? "Odds credits exhausted — add a new free Odds API key, then Fetch again later."
                : "WARNING: spends ~8 Odds credits. Confirm before running. Prefer Scan/Rescore (free). 20m cooldown after each Fetch."
            }
            className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-100 hover:bg-rose-500/20 disabled:opacity-50"
          >
            {loading === "live" ? "Fetching…" : "Fetch live odds (uses credits)"}
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
            title="Atlas Insight ranks FanDuel-verified open markets (also runs automatically after Fetch live odds)."
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
          >
            {loading === "openai" ? "Atlas Insight verifying…" : "Atlas Insight"}
          </button>
        </div>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <SportsCategoryTabs
          categories={categories}
          activeSlug={activeCategory}
          onSelect={(slug) => void handleCategoryChange(slug)}
        />

        <SportFilterTabs
          items={items}
          activeSport={activeSport}
          onSelect={(sport) => void handleSportChange(sport)}
          extraLeagues={oddsStatus?.league_catalog ?? oddsStatus?.near_term_leagues ?? []}
        />
      </div>
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
          title={
            activeCategory || activeSport || filter !== "all" || window !== "all"
              ? "No plays match these filters"
              : "No upcoming sports plays"
          }
          description={
            window === "today" && !activeCategory && filter === "all" && !activeSport
              ? filterByWindow(items, "soon").length > 0
                ? `Nothing in the next 24 hours. ${filterByWindow(items, "soon").length} play(s) are in Next 48h — open that window, or Repair for tonight's live odds.`
                : "Nothing in the next 24 hours on the board. Tap Repair sports board to Fetch live odds for Today's slate."
              : window === "soon" && !activeCategory && filter === "all" && !activeSport
                ? "No plays in the next 48 hours. Try This week, Next 30 days, or All dates."
                : activeCategory || activeSport || filter !== "all"
                  ? "Try All leagues, All bet types, or widen the Window (Next 48h / Next 30 days / All dates)."
                  : "Use Repair sports board if picks vanished after a redeploy. Fetch live odds seeds FanDuel/DraftKings lines; Rescore re-ranks free; Atlas Insight adds analyst consensus."
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {window === "today" && filterByWindow(items, "soon").length > 0 ? (
                <button
                  type="button"
                  onClick={() => void handleWindowChange("soon")}
                  className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-4 py-2 text-sm font-semibold text-emerald-100"
                >
                  Show Next 48h
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => void repairSportsBoard()}
                disabled={busy || fetchBlocked}
                className="rounded-lg border border-amber-500/50 bg-amber-500/15 px-4 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
              >
                {loading === "repair" ? "Repairing…" : "Repair sports board"}
              </button>
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
                {loading === "openai" ? "Atlas Insight searching…" : "Atlas Insight"}
              </button>
            </div>
          }
        />
      )}
    </div>
  );
}
