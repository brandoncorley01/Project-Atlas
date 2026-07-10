"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ParlayCard, type Parlay } from "@/components/parlays/ParlayCard";
import { ParlayCategoryTabs } from "@/components/parlays/ParlayCategoryTabs";
import { ParlayStyleTabs } from "@/components/parlays/ParlayStyleTabs";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { SectionHeader } from "@/components/ui/SectionHeader";
import type { ParlayCategoryMeta } from "@/lib/parlay-categories";
import {
  emptyParlayCategoryCatalog,
  mergeParlayCategoryCatalog,
  PARLAY_CATEGORY_LABELS,
} from "@/lib/parlay-categories";
import {
  buildParlayStyleCatalog,
  emptyParlayStyleCatalog,
  PARLAY_STYLE_LABELS,
  PARLAY_STYLE_DEFINITIONS,
  type ParlayStyleMeta,
} from "@/lib/parlay-styles";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

interface ParlaysViewProps {
  initialItems: Parlay[];
  initialCategories?: ParlayCategoryMeta[];
}

interface ParlaySection {
  key: string;
  title: string;
  items: Parlay[];
}

function buildSections(items: Parlay[]): ParlaySection[] {
  const styleOrder = ["conservative", "balanced", "aggressive"] as const;
  const catOrder = ["today", "next_48h", "multi_day"] as const;
  const sections: ParlaySection[] = [];

  for (const style of styleOrder) {
    for (const cat of catOrder) {
      const filtered = items.filter(
        (p) => p.style === style && (p.categories ?? []).includes(cat),
      );
      if (!filtered.length) continue;
      sections.push({
        key: `${style}-${cat}`,
        title: `${PARLAY_STYLE_LABELS[style] ?? style} · ${PARLAY_CATEGORY_LABELS[cat] ?? cat}`,
        items: filtered,
      });
    }
    const uncategorized = items.filter(
      (p) =>
        p.style === style &&
        !(p.categories ?? []).some((c) => catOrder.includes(c as (typeof catOrder)[number])),
    );
    if (uncategorized.length) {
      sections.push({
        key: `${style}-other`,
        title: `${PARLAY_STYLE_LABELS[style] ?? style} · Other`,
        items: uncategorized,
      });
    }
  }
  return sections;
}

export function ParlaysView({
  initialItems,
  initialCategories = emptyParlayCategoryCatalog(),
}: ParlaysViewProps) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [categories, setCategories] = useState(initialCategories);
  const [styles, setStyles] = useState<ParlayStyleMeta[]>(emptyParlayStyleCatalog());
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [activeStyle, setActiveStyle] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const syncMeta = useCallback(
    (nextItems: Parlay[], apiCategories?: ParlayCategoryMeta[]) => {
      setCategories(mergeParlayCategoryCatalog(apiCategories, nextItems));
      setStyles(buildParlayStyleCatalog(nextItems));
    },
    [],
  );

  const loadCategories = useCallback(async (token?: string) => {
    const apiUrl = getApiUrl();
    const res = await fetch(`${apiUrl}/parlays/categories`, {
      headers: apiRequestHeaders(token),
    });
    if (res.ok) {
      const data = await res.json();
      return (data.categories ?? []) as ParlayCategoryMeta[];
    }
    return undefined;
  }, []);

  const loadItems = useCallback(
    async (token?: string, style?: string | null, category?: string | null) => {
      const apiUrl = getApiUrl();
      const params = new URLSearchParams({ limit: "50" });
      if (category) params.set("category", category);
      if (style) params.set("style", style);
      const res = await fetch(`${apiUrl}/parlays?${params}`, {
        headers: apiRequestHeaders(token),
      });
      if (res.ok) {
        const data = await res.json();
        return (data.items ?? []) as Parlay[];
      }
      return null;
    },
    [],
  );

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  useEffect(() => {
    syncMeta(initialItems, initialCategories);
  }, [initialItems, initialCategories, syncMeta]);

  const sections = useMemo(() => {
    if (activeStyle || activeCategory) return null;
    return buildSections(items);
  }, [items, activeStyle, activeCategory]);

  async function refreshList(
    token?: string,
    style: string | null = activeStyle,
    category: string | null = activeCategory,
  ) {
    const nextItems = await loadItems(token, style, category);
    if (nextItems != null) {
      setItems(nextItems);
      const apiCategories = await loadCategories(token);
      syncMeta(nextItems, apiCategories);
    }
  }

  async function handleCategoryChange(slug: string | null) {
    setActiveCategory(slug);
    const token = await getToken();
    await refreshList(token, activeStyle, slug);
  }

  async function handleStyleChange(slug: string | null) {
    setActiveStyle(slug);
    const token = await getToken();
    await refreshList(token, slug, activeCategory);
  }

  async function buildParlays() {
    setLoading(true);
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(false);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/build-parlays`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        signal: AbortSignal.timeout(180000),
      });
      const body = await res.json();
      if (!res.ok) {
        const detail = typeof body.detail === "string" ? body.detail : "Build failed";
        setMessage(
          res.status === 404
            ? "Build endpoint not found — restart API with .\\scripts\\restart-api.ps1"
            : detail,
        );
        setLoading(false);
        return;
      }

      const created = body.parlays_created as number;
      const pool = body.sports_pool as number | undefined;
      const builtItems = (body.items as Parlay[] | undefined) ?? [];

      if (created > 0) {
        setMessage(
          `Built ${created} parlay options from ${pool ?? "?"} sports plays — Today, 24–48h, and multi-day across conservative, balanced & aggressive.`,
        );
        setActiveCategory(null);
        setActiveStyle(null);
        if (builtItems.length > 0) {
          setItems(builtItems);
          syncMeta(builtItems);
        } else {
          await refreshList(token, null, null);
        }
      } else {
        setMessage(
          (body.message as string) ??
            (pool != null && pool < 2
              ? "Need at least 2 upcoming sports plays — run Scan sports odds first"
              : "Could not build parlays from current signals"),
        );
      }

      router.refresh();
    } catch {
      setMessage("Backend not responding — restart API with .\\scripts\\restart-api.ps1");
    }
    setLoading(false);
  }

  let globalRank = 0;

  return (
    <div>
      <div className="mb-4 rounded-xl border border-orange-500/30 bg-orange-500/8 px-4 py-3">
        <p className="text-sm font-semibold text-orange-200">Parlays in 2 steps</p>
        <ol className="mt-2 list-inside list-decimal space-y-1 text-sm text-muted">
          <li>Run <strong className="text-foreground">Scan sports odds</strong> on the Sports page first</li>
          <li>Come back here and click <strong className="text-foreground">Build parlay options</strong></li>
        </ol>
        <p className="mt-2 text-xs text-muted">
          Conservative = 2 legs (safest) · Balanced = 3 legs · Aggressive = 4 legs (biggest payout)
        </p>
        <p className="mt-2 text-xs text-muted">
          ☆ <strong className="text-foreground">Save to watchlist</strong> on any ticket to track it, or build a custom parlay on{" "}
          <Link href="/sports" className="text-accent hover:underline">
            Sports
          </Link>
          . View saved picks on{" "}
          <Link href="/watchlist?tab=parlays" className="text-accent hover:underline">
            Watchlist → Parlays
          </Link>
          .
        </p>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Atlas builds many parlay tickets from every sports play — conservative (2-leg), balanced
          (3-leg), and aggressive (4-leg) in <strong>Today</strong>, <strong>24–48h</strong>, and{" "}
          <strong>multi-day</strong> windows. Small stake → large payout when all legs hit.
        </p>
        <button
          type="button"
          onClick={buildParlays}
          disabled={loading}
          className="shrink-0 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm disabled:opacity-50"
        >
          {loading ? "Building parlays…" : "Build parlay options"}
        </button>
      </div>

      <ParlayStyleTabs styles={styles} activeSlug={activeStyle} onSelect={handleStyleChange} />

      {activeStyle && (
        <div className="mb-4 rounded-xl border border-orange-500/30 bg-orange-500/8 px-4 py-3">
          <p className="text-sm font-semibold text-orange-200">
            {PARLAY_STYLE_LABELS[activeStyle] ?? activeStyle} parlays
          </p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {PARLAY_STYLE_DEFINITIONS.find((s) => s.slug === activeStyle)?.description ??
              "Filtered by risk tier."}
          </p>
        </div>
      )}

      <ParlayCategoryTabs
        categories={categories}
        activeSlug={activeCategory}
        onSelect={handleCategoryChange}
      />

      {message && (
        <p className="mb-4 rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-muted">
          {message}
        </p>
      )}

      {loading && items.length === 0 ? (
        <ListSkeleton count={3} />
      ) : items.length > 0 ? (
        sections ? (
          <div className="space-y-10">
            {sections.map((section) => (
              <section key={section.key}>
                <SectionHeader title={section.title} />
                <div className="space-y-4">
                  {section.items.map((item) => {
                    globalRank += 1;
                    return <ParlayCard key={item.id} row={item} rank={globalRank} />;
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {items.map((item, index) => (
              <ParlayCard key={item.id} row={item} rank={index + 1} />
            ))}
          </div>
        )
      ) : (
        <EmptyState
          title={activeCategory || activeStyle ? "No parlays match these filters" : "No parlays yet"}
          description={
            activeCategory || activeStyle ? (
              <>
                Try <strong>All tiers</strong> and <strong>All parlays</strong>, or click{" "}
                <strong>Build parlay options</strong>.
              </>
            ) : (
              <>
                Run <strong>Scan sports odds</strong>, then <strong>Build parlay options</strong> to
                generate dozens of tickets from your plays.
              </>
            )
          }
          action={
            !activeCategory && !activeStyle ? (
              <button
                type="button"
                onClick={buildParlays}
                disabled={loading}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Build parlay options
              </button>
            ) : undefined
          }
        />
      )}
    </div>
  );
}
