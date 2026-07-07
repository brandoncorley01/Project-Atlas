"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { NewsCard, type NewsItem } from "@/components/news/NewsCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { TermHint } from "@/components/ui/TermHint";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

interface NewsBoardProps {
  initialItems: NewsItem[];
}

function needsLivePrices(items: NewsItem[]): boolean {
  return items.some((item) => {
    const companies =
      item.affected_companies ??
      item.related_tickers.map((symbol) => ({ symbol, price: null, change: null, change_pct: null }));
    return companies.some((co) => co.symbol && co.price == null);
  });
}

export function NewsBoard({ initialItems }: NewsBoardProps) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [sentiment, setSentiment] = useState<string>("all");
  const [minImpact, setMinImpact] = useState(0);

  useEffect(() => {
    if (!needsLivePrices(initialItems)) {
      return;
    }

    let cancelled = false;
    async function loadPrices() {
      const apiUrl = getApiUrl();
      try {
        const res = await fetch(`${apiUrl}/news?limit=40`, {
          headers: apiRequestHeaders(),
        });
        if (!res.ok || cancelled) {
          return;
        }
        const listData = await res.json();
        if (!cancelled) {
          setItems(listData.items ?? []);
        }
      } catch {
        // Keep SSR items if live quote refresh fails.
      }
    }

    void loadPrices();
    return () => {
      cancelled = true;
    };
  }, [initialItems]);

  const filtered = useMemo(() => {
    return items
      .filter((item) => (sentiment === "all" ? true : item.sentiment === sentiment))
      .filter((item) => item.impact_score >= minImpact)
      .sort((a, b) => b.impact_score + b.time_sensitivity_score * 0.3 - (a.impact_score + a.time_sensitivity_score * 0.3));
  }, [items, sentiment, minImpact]);

  async function refreshNews() {
    setLoading(true);
    setMessage(null);

    let token: string | undefined;
    if (!usesBffProxy()) {
      const { createClient } = await import("@/lib/supabase/client");
      const { data } = await createClient().auth.getSession();
      token = data.session?.access_token ?? undefined;
      if (!token) {
        setMessage("Not signed in");
        setLoading(false);
        return;
      }
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-news`, {
        method: "POST",
        headers: apiRequestHeaders(token),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : "Refresh failed");
        setLoading(false);
        return;
      }
      setMessage(`Loaded ${data.news_created ?? 0} stories · ${data.high_impact ?? 0} high impact`);

      const listRes = await fetch(`${apiUrl}/news?limit=40`, {
        headers: apiRequestHeaders(token),
      });
      if (listRes.ok) {
        const listData = await listRes.json();
        setItems(listData.items ?? []);
      }
      router.refresh();
    } catch {
      setMessage("Backend not responding — run .\\scripts\\start-dev.ps1");
    }
    setLoading(false);
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-wrap gap-2">
          <label className="flex flex-col gap-1 text-xs text-muted">
            <TermHint term="sentiment" label="Sentiment filter" />
            <select
              value={sentiment}
              onChange={(e) => setSentiment(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="all">All</option>
              <option value="bullish">Bullish</option>
              <option value="bearish">Bearish</option>
              <option value="neutral">Neutral</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            <TermHint term="impact" label="Min impact" />
            <select
              value={minImpact}
              onChange={(e) => setMinImpact(Number(e.target.value))}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              <option value={0}>Any impact</option>
              <option value={45}>45+ moderate</option>
              <option value={60}>60+ high</option>
              <option value={75}>75+ urgent</option>
            </select>
          </label>
        </div>
        <button
          type="button"
          onClick={refreshNews}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Refreshing news…" : "Refresh news feed"}
        </button>
      </div>

      {message && <p className="mb-4 text-sm text-muted">{message}</p>}

      {filtered.length > 0 ? (
        <div className="space-y-3">
          {filtered.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No news stories yet"
          description="Click Refresh news feed to pull headlines from Finnhub and RSS. Every story links to the original article so you can read more."
          action={
            <button
              type="button"
              onClick={refreshNews}
              disabled={loading}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Refresh news feed
            </button>
          }
        />
      )}
    </div>
  );
}
