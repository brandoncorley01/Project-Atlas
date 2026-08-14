"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ScanActionButton, ScanToolbarGroup } from "@/components/dashboard/ScanActionButton";
import { getApiUrl, usesBffProxy, apiRequestHeaders } from "@/lib/api-url";

type ScanMode = "live" | "mock" | "news" | "stocks" | "sports" | "parlays" | "sports-pipeline";

function engineSucceeded(httpOk: boolean, data: Record<string, unknown>): boolean {
  if (!httpOk) return false;
  if (data.ok === false) return false;
  if (data.status === "error") return false;
  return true;
}

function engineFailureMessage(data: Record<string, unknown>, fallback: string): string {
  if (typeof data.message === "string" && data.message.trim()) return data.message.trim();
  if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();
  if (typeof data.error === "string" && data.error.trim()) return data.error.trim();
  return fallback;
}

export function SignalsActions() {
  const router = useRouter();
  const [loading, setLoading] = useState<ScanMode | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  async function postEngine(path: string): Promise<{
    ok: boolean;
    data: Record<string, unknown>;
    status: number;
  }> {
    const token = await getToken();
    if (!usesBffProxy() && !token) {
      return { ok: false, data: { detail: "Not signed in" }, status: 401 };
    }

    const apiUrl = getApiUrl();
    try {
      const response = await fetch(`${apiUrl}${path}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        signal: AbortSignal.timeout(300000),
      });
      let data: Record<string, unknown> = {};
      try {
        data = (await response.json()) as Record<string, unknown>;
      } catch {
        return { ok: false, data: { detail: "Invalid response from API" }, status: response.status };
      }
      return {
        ok: engineSucceeded(response.ok, data),
        data,
        status: response.status,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      const timedOut =
        msg.includes("timeout") ||
        msg.includes("aborted") ||
        (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError"));
      if (timedOut) {
        return {
          ok: false,
          data: {
            detail: usesBffProxy()
              ? "Scan timed out — try again, or run modules one at a time from their pages."
              : "Request timed out — run .\\scripts\\restart-api.ps1",
          },
          status: 0,
        };
      }
      if (msg.includes("fetch")) {
        return { ok: false, data: { detail: "Backend not responding — run .\\scripts\\start-dev.ps1" }, status: 0 };
      }
      return { ok: false, data: { detail: msg }, status: 0 };
    }
  }

  function formatResult(mode: ScanMode, data: Record<string, unknown>): string {
    const scanned = data.stats as {
      symbols_scanned?: number;
      universe_size?: number;
      deep_dive_symbols?: number;
    } | undefined;
    const topProb = data.top_profit_probability as number | undefined;
    const extra =
      scanned?.universe_size != null
        ? ` · ${scanned.universe_size} names screened`
        : scanned?.symbols_scanned != null
          ? ` · ${scanned.symbols_scanned} symbols`
          : "";
    const probExtra = topProb != null ? ` · top ${topProb.toFixed(0)}% win prob` : "";
    const budget = data.budget_signals as number | undefined;
    const budgetExtra = budget != null && budget > 0 ? ` · ${budget} under $100` : "";
    const newsCreated = data.news_created as number | undefined;
    const highImpact = data.high_impact as number | undefined;
    const created = (data.signals_created as number | undefined) ?? 0;
    const parlaysCreated = data.parlays_created as number | undefined;
    const apiMessage = data.message as string | undefined;

    if (apiMessage && created === 0 && (parlaysCreated ?? 0) === 0) return apiMessage;

    switch (mode) {
      case "news":
        return `News updated · ${newsCreated ?? 0} stories (${highImpact ?? 0} high impact)`;
      case "stocks": {
        const topOpp = data.top_opportunity as number | undefined;
        return `Found ${created} stock swings${topOpp != null ? ` · top ${topOpp.toFixed(0)}/100` : ""}`;
      }
      case "sports": {
        const topOpp = data.top_opportunity as number | undefined;
        const cacheUsed = data.cache_used as boolean | undefined;
        const creditsUsed = data.credits_used as number | undefined;
        const creditExtra = cacheUsed ? " · cached" : creditsUsed != null ? ` · ~${creditsUsed} credits` : "";
        return created > 0
          ? `Found ${created} sports plays${topOpp != null ? ` · top ${topOpp.toFixed(0)}/100` : ""}${creditExtra}`
          : (apiMessage ?? "No +EV edges found");
      }
      case "parlays": {
        const styles = data.styles_built as string[] | undefined;
        const count = parlaysCreated ?? 0;
        return count > 0
          ? `Built ${count} parlays${styles?.length ? ` (${styles.join(", ")})` : ""}`
          : (apiMessage ?? "Scan sports first");
      }
      case "mock":
        return `Generated ${created} mock signals`;
      case "live":
      default:
        return `Options scan complete · ${created} signals${extra}${probExtra}${budgetExtra}`;
    }
  }

  async function runScan(path: string, mode: ScanMode) {
    setLoading(mode);
    setMessage(null);
    setMenuOpen(false);

    const { ok, data, status } = await postEngine(path);
    setLoading(null);

    if (!ok) {
      let text = engineFailureMessage(data, "Request failed");
      if (text.includes("getaddrinfo") || text.includes("11004")) {
        text =
          "Network/DNS error on the PC running the API. Check internet, tap Restart, then try again.";
      }
      setMessage(status === 404 ? "Endpoint not found — run .\\scripts\\start-dev.ps1" : text);
      return;
    }

    const userMessage = typeof data.message === "string" ? data.message : null;
    if (userMessage && (data.signals_created === 0 || data.parlays_created === 0)) {
      setMessage(userMessage);
    } else {
      setMessage(formatResult(mode, data));
    }
    router.refresh();
    window.dispatchEvent(new Event("atlas:dashboard-refresh"));
  }

  async function runSportsPipeline() {
    setLoading("sports-pipeline");
    setMessage(null);
    setMenuOpen(false);

    const sports = await postEngine("/engine/refresh-sports?cache_only=true");
    if (!sports.ok) {
      setLoading(null);
      let text = engineFailureMessage(sports.data, "Sports scan failed");
      if (text.includes("getaddrinfo") || text.includes("11004")) {
        text =
          "Network/DNS error on the PC running the API. Check internet, tap Restart, then try again.";
      }
      setMessage(text);
      return;
    }

    const zeroSignalsMessage = typeof sports.data.message === "string" ? sports.data.message : null;
    if (zeroSignalsMessage && sports.data.signals_created === 0) {
      setLoading(null);
      setMessage(zeroSignalsMessage);
      router.refresh();
      window.dispatchEvent(new Event("atlas:dashboard-refresh"));
      return;
    }

    const parlays = await postEngine("/engine/build-parlays");
    setLoading(null);

    if (!parlays.ok) {
      setMessage(
        `${formatResult("sports", sports.data)} · parlays failed: ${engineFailureMessage(parlays.data, "error")}`,
      );
      router.refresh();
      window.dispatchEvent(new Event("atlas:dashboard-refresh"));
      return;
    }

    const sportsMsg = formatResult("sports", sports.data);
    const parlayMsg = formatResult("parlays", parlays.data);
    setMessage(`${sportsMsg} · ${parlayMsg}`);
    router.refresh();
    window.dispatchEvent(new Event("atlas:dashboard-refresh"));
  }

  const busy = loading !== null;

  return (
    <div className="flex w-full flex-col gap-3 lg:w-auto lg:items-end">
      <div className="flex flex-wrap items-end gap-2 sm:gap-3">
        <ScanToolbarGroup label="Equities">
          <ScanActionButton
            label="Options"
            loadingLabel="Scanning…"
            loading={loading === "live"}
            disabled={busy && loading !== "live"}
            variant="primary"
            onClick={() => runScan("/engine/refresh-options", "live")}
            title="Deep scan options chains and rank by edge"
          />
          <ScanActionButton
            label="Stocks"
            loadingLabel="Scanning…"
            loading={loading === "stocks"}
            disabled={busy && loading !== "stocks"}
            onClick={() => runScan("/engine/refresh-stocks", "stocks")}
            title="Scan swing setups on movers and watchlist"
          />
        </ScanToolbarGroup>

        <ScanToolbarGroup label="Sports">
          <ScanActionButton
            label="Odds + Parlays"
            loadingLabel={loading === "sports-pipeline" ? "Running…" : "Scanning…"}
            loading={loading === "sports" || loading === "parlays" || loading === "sports-pipeline"}
            disabled={busy && !["sports", "parlays", "sports-pipeline"].includes(loading ?? "")}
            onClick={runSportsPipeline}
            title="Scan sports odds, then auto-build parlay tickets"
          />
        </ScanToolbarGroup>

        <ScanToolbarGroup label="Intel">
          <ScanActionButton
            label="News"
            loadingLabel="Refreshing…"
            loading={loading === "news"}
            disabled={busy && loading !== "news"}
            variant="ghost"
            onClick={() => runScan("/engine/refresh-news", "news")}
            title="Refresh Finnhub and RSS headlines"
          />
        </ScanToolbarGroup>

        <div className="relative self-end" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            disabled={busy}
            className="rounded-lg border border-border bg-background/60 px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-hover hover:text-foreground disabled:opacity-45"
            aria-expanded={menuOpen}
            aria-label="More scan actions"
          >
            ···
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-20 mt-1 min-w-[10rem] rounded-lg border border-border bg-surface-elevated py-1 shadow-lg">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-xs text-muted hover:bg-surface-hover hover:text-foreground"
                onClick={() => runScan("/engine/refresh-sports?cache_only=true", "sports")}
              >
                Sports only (no parlays)
              </button>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-xs text-muted hover:bg-surface-hover hover:text-foreground"
                onClick={() => runScan("/engine/build-parlays", "parlays")}
              >
                Build parlays only
              </button>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-xs text-muted hover:bg-surface-hover hover:text-foreground"
                onClick={() => runScan("/engine/run-mock", "mock")}
              >
                Mock demo data
              </button>
            </div>
          )}
        </div>
      </div>

      {message && (
        <p className="w-full rounded-lg border border-border/80 bg-background/50 px-3 py-2 text-xs leading-relaxed text-muted lg:max-w-md lg:text-right">
          {message}
        </p>
      )}
    </div>
  );
}
