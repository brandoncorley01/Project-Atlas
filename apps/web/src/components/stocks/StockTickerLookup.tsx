"use client";

import { useEffect, useRef, useState } from "react";
import { StockSignalCard, type StockSignal } from "@/components/stocks/StockSignalCard";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

interface AnalyzeStockResponse {
  status: string;
  ok?: boolean;
  message?: string;
  item?: StockSignal;
  weak_setup?: boolean;
}

export function StockTickerLookup({ initialTicker }: { initialTicker?: string }) {
  const [ticker, setTicker] = useState(initialTicker?.toUpperCase() ?? "");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<StockSignal | null>(null);
  const autoRan = useRef(false);

  useEffect(() => {
    if (initialTicker && !autoRan.current) {
      autoRan.current = true;
      void analyze(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once for deep link ticker
  }, [initialTicker]);

  async function analyze(persist = false) {
    const sym = ticker.trim().toUpperCase();
    if (!sym) {
      setMessage("Enter a ticker symbol.");
      return;
    }

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
    const params = new URLSearchParams({ ticker: sym, persist: String(persist) });
    try {
      const res = await fetch(`${apiUrl}/engine/analyze-stock?${params}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        signal: AbortSignal.timeout(120_000),
      });
      const body = (await res.json()) as AnalyzeStockResponse;
      if (!res.ok || body.status === "error" || !body.item) {
        setMessage(body.message ?? "Analysis failed — check the ticker and try again.");
        setResult(null);
        setLoading(false);
        return;
      }

      setResult(body.item);
      setMessage(body.message ?? `${sym} analysis ready.`);
    } catch {
      setMessage("Backend not responding — restart the API and try again.");
      setResult(null);
    }
    setLoading(false);
  }

  return (
    <section className="mb-8 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label htmlFor="stock-ticker" className="text-sm font-semibold text-foreground">
            Analyze any ticker
          </label>
          <p className="mt-1 text-xs text-muted">
            Full swing analysis — chart, entry zone, stop-loss, take-profit targets, RSI, MACD, and news catalyst.
          </p>
          <input
            id="stock-ticker"
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter") void analyze(false);
            }}
            placeholder="e.g. AAPL, NVDA, TSLA"
            className="mt-3 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium uppercase tracking-wide outline-none focus:border-emerald-500"
            maxLength={12}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void analyze(false)}
            disabled={loading}
            className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
          <button
            type="button"
            onClick={() => void analyze(true)}
            disabled={loading}
            title="Save this analysis to your active stock picks"
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            Save pick
          </button>
        </div>
      </div>

      {message && (
        <p className="mt-3 text-sm text-muted">{message}</p>
      )}

      {result && (
        <div className="mt-5 border-t border-emerald-500/20 pt-5">
          <StockSignalCard row={result} rank={1} lookupMode showChart />
        </div>
      )}
    </section>
  );
}
