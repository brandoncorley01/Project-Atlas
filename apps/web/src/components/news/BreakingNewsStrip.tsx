"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { NewsCard, type NewsItem } from "@/components/news/NewsCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiRequestHeaders, getApiUrl } from "@/lib/api-url";

function needsLivePrices(items: NewsItem[]): boolean {
  return items.some((item) => {
    const companies =
      item.affected_companies ??
      item.related_tickers.map((symbol) => ({ symbol, price: null, change: null, change_pct: null }));
    return companies.some((co) => co.symbol && co.price == null);
  });
}

export function BreakingNewsStrip({ items: initialItems }: { items: NewsItem[] }) {
  const [items, setItems] = useState(initialItems);

  useEffect(() => {
    if (!needsLivePrices(initialItems)) {
      return;
    }

    let cancelled = false;
    async function loadPrices() {
      const apiUrl = getApiUrl();
      try {
        const res = await fetch(`${apiUrl}/news?limit=5&min_impact=45`, {
          headers: apiRequestHeaders(),
        });
        if (!res.ok || cancelled) {
          return;
        }
        const payload = await res.json();
        if (!cancelled) {
          setItems(payload.items ?? []);
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

  if (items.length === 0) {
    return (
      <EmptyState
        compact
        title="No breaking news yet"
        description="Headlines appear here after you refresh the news feed. Each story links to the original article."
        action={
          <Link
            href="/news"
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-500/90"
          >
            Open News board
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <NewsCard key={item.id} item={item} compact />
      ))}
      <Link
        href="/news"
        className="inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline"
      >
        View all news with live prices →
      </Link>
    </div>
  );
}
