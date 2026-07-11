"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { StockTickerLookup } from "@/components/stocks/StockTickerLookup";
import { StockSignalCard, type StockSignal } from "@/components/stocks/StockSignalCard";
import { AtlasModuleInsight } from "@/components/ai/AtlasModuleInsight";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

interface StocksSignalsViewProps {
  initialItems: StockSignal[];
  initialTicker?: string;
}

export function StocksSignalsView({ initialItems, initialTicker }: StocksSignalsViewProps) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshStocks() {
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
      const res = await fetch(`${apiUrl}/engine/refresh-stocks`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        signal: AbortSignal.timeout(300000),
      });
      const body = await res.json();
      if (!res.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Scan failed");
        setLoading(false);
        return;
      }

      const created = body.signals_created as number;
      const scanned = body.symbols_scanned as number | undefined;
      setMessage(
        created > 0
          ? `Found ${created} swing setups · scanned ${scanned ?? "?"} symbols`
          : (body.message as string) ?? "No setups met the score threshold",
      );

      const listRes = await fetch(`${apiUrl}/signals/stocks?limit=20`, {
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
      <StockTickerLookup initialTicker={initialTicker} />

      <AtlasModuleInsight
        module="stock"
        signalId={items[0]?.id}
        headline={
          items[0]
            ? `#1 ${items[0].ticker ?? "swing"} — technicals + catalyst thesis`
            : "Scan swings — Atlas ranks RSI/MACD setups like sports Insight ranks props."
        }
        urgencyNote={
          items[0]?.opportunity_score != null && items[0].opportunity_score >= 70
            ? "High opportunity score — review entry/stop before the move extends."
            : null
        }
      />

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Ranked by opportunity · RSI, MACD, relative volume, and news catalysts.
        </p>
        <button
          type="button"
          onClick={refreshStocks}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Scanning stocks…" : "Scan stock swings"}
        </button>
      </div>

      {message && <p className="mb-4 text-sm text-muted">{message}</p>}

      {loading && items.length === 0 ? (
        <ListSkeleton count={3} />
      ) : items.length > 0 ? (
        <div className="space-y-4">
          {items.map((item, index) => (
            <StockSignalCard key={item.id} row={item} rank={index + 1} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No stock swings yet"
          description="Click Scan stock swings to analyze movers and watchlist names. Atlas ranks setups by RSI, MACD, volume, and news catalysts."
          action={
            <button
              type="button"
              onClick={refreshStocks}
              disabled={loading}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Scan stock swings
            </button>
          }
        />
      )}
    </div>
  );
}
