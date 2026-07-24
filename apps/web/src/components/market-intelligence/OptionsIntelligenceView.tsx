"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { DataStatusBadge, FreshnessLine } from "@/components/market-intelligence/DataStatusBadge";
import { HeatmapPanel } from "@/components/market-intelligence/HeatmapPanel";
import { OptionsTradeCard } from "@/components/market-intelligence/OptionsTradeCard";
import {
  fetchAlertSettings,
  fetchLowPremium,
  fetchOptionsFlow,
  fetchOptionsHeatmap,
  fetchOptionsPerformance,
  fetchSignalHistory,
  fetchSmartMoney,
  type Freshness,
} from "@/lib/market-intelligence-api";

const TABS = [
  { id: "flow", label: "Flow Scanner" },
  { id: "low-premium", label: "Low-Premium" },
  { id: "smart-money", label: "Smart-Money Watchlist" },
  { id: "heatmap", label: "Options Heatmap" },
  { id: "history", label: "Signal History" },
  { id: "performance", label: "Performance" },
  { id: "alerts", label: "Alert Settings" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function OptionsIntelligenceView() {
  const search = useSearchParams();
  const initial = (search.get("tab") as TabId) || "flow";
  const [tab, setTab] = useState<TabId>(TABS.some((t) => t.id === initial) ? initial : "flow");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [flow, setFlow] = useState<Record<string, unknown>[]>([]);
  const [lowPremium, setLowPremium] = useState<Record<string, unknown>[]>([]);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown>[]>([]);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [performance, setPerformance] = useState<Record<string, unknown> | null>(null);
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>([]);
  const [usingFixture, setUsingFixture] = useState(false);

  const load = useCallback(async (active: TabId) => {
    setLoading(true);
    setError(null);
    try {
      if (active === "flow") {
        const data = await fetchOptionsFlow();
        if (!data) throw new Error("Could not load flow scanner");
        setFlow(data.items ?? []);
        setFreshness(data.freshness ?? null);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "low-premium") {
        const data = await fetchLowPremium();
        if (!data) throw new Error("Could not load low-premium opportunities");
        setLowPremium((data.items ?? []).map((i) => ({ ...(i.event as object), ...(i as object) })));
        setFreshness(data.freshness ?? null);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "smart-money") {
        const data = await fetchSmartMoney();
        if (!data) throw new Error("Could not load smart-money watchlist");
        setSmartMoney(data.items ?? []);
        setFreshness(data.freshness ?? null);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "heatmap") {
        const data = await fetchOptionsHeatmap();
        if (!data) throw new Error("Could not load options heatmap");
        setHeatmap(data);
        setFreshness((data.freshness as Freshness) ?? null);
        setDisclaimer(String(data.disclaimer ?? ""));
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "history") {
        const data = await fetchSignalHistory();
        if (!data) throw new Error("Could not load signal history");
        setHistory(data.items ?? []);
        setFreshness(data.freshness ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "performance") {
        const data = await fetchOptionsPerformance();
        if (!data) throw new Error("Could not load performance analytics");
        setPerformance(data);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "alerts") {
        const data = await fetchAlertSettings();
        if (!data) throw new Error("Could not load alert settings");
        setAlerts(data.items ?? []);
        setUsingFixture(data.source === "client_fixture");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const lowPremiumCards = useMemo(() => {
    return lowPremium.map((row) => {
      if (row.event && typeof row.event === "object") {
        const event = row.event as Record<string, unknown>;
        const score = row.score as Record<string, unknown> | undefined;
        return {
          ticker: event.underlying,
          contract: `${event.underlying} ${event.expiration} ${event.strike} ${String(event.option_type).toUpperCase()}`,
          direction: row.direction,
          current_premium: event.contract_price ?? event.midpoint,
          estimated_total_premium: event.estimated_premium,
          bid_ask_spread_pct: row.spread_pct,
          volume: event.contract_volume,
          open_interest: event.open_interest,
          volume_oi_ratio: event.volume_oi_ratio,
          unusual_score: score?.final_score,
          atlas_confidence: score?.confidence,
          risk_level: "moderate",
          liquidity_grade: "B",
          explanation: `Rank score ${row.rank_score}. Affordable contract with unusualness confirmation — cheap alone does not qualify.`,
          warnings: (score?.penalties as string[]) ?? [],
          suggested_review_zone: row.review_zone,
          data_status: event.data_status,
          score,
        } as Record<string, unknown>;
      }
      return row;
    });
  }, [lowPremium]);

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Options Intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Affordable retail options decision support — unusual activity, liquidity filters, and
          explainable scores. Activity does not prove intent; large trades may be hedges or spreads.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <DataStatusBadge freshness={freshness} />
          <FreshnessLine freshness={freshness} />
        </div>
        {usingFixture && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            Preview mode: showing <strong>simulated</strong> fixtures because the Market Intelligence
            API is not on this environment yet. Merge PR #8 and deploy the API (plus apply the
            Supabase migration) for live/delayed provider data. Direct links:{" "}
            <Link href="/options-intelligence" className="underline">
              Options Intelligence
            </Link>{" "}
            ·{" "}
            <Link href="/market-intelligence" className="underline">
              Market Intelligence
            </Link>
          </div>
        )}
      </header>

      <div className="flex gap-1 overflow-x-auto pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-sm ${
              tab === t.id
                ? "bg-accent/20 font-medium text-accent"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-muted">Loading…</p>}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
          {error}
        </div>
      )}
      {disclaimer && <p className="text-xs text-muted">{disclaimer}</p>}

      {!loading && tab === "flow" && (
        <div className="grid gap-3">
          {flow.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
          ))}
          {flow.length === 0 && <EmptyState message="No flow events available from the active provider." />}
        </div>
      )}

      {!loading && tab === "low-premium" && (
        <div className="grid gap-3">
          {lowPremiumCards.map((card, idx) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? idx)} card={card} />
          ))}
          {lowPremiumCards.length === 0 && (
            <EmptyState message="No contracts passed liquidity / unusualness filters." />
          )}
        </div>
      )}

      {!loading && tab === "smart-money" && (
        <div className="grid gap-3">
          {smartMoney.map((row) => (
            <article key={String(row.underlying)} className="rounded-xl border border-border bg-surface/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">{String(row.underlying)}</h3>
                <DataStatusBadge status={String(row.data_status ?? "")} />
              </div>
              <p className="mt-1 text-sm font-medium text-foreground">{String(row.label)}</p>
              <p className="mt-2 text-xs text-muted">
                Score {String(row.unusual_score)} · Confidence {String(row.confidence)} · Premium $
                {String(row.total_premium)}
              </p>
              <ul className="mt-2 space-y-1 text-xs text-muted">
                {(Array.isArray(row.evidence) ? (row.evidence as string[]) : []).map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
              <p className="mt-2 text-[11px] text-amber-200/80">{String(row.disclaimer)}</p>
            </article>
          ))}
          {smartMoney.length === 0 && <EmptyState message="No concentrated activity clusters yet." />}
        </div>
      )}

      {!loading && tab === "heatmap" && heatmap && (
        <HeatmapPanel
          title="Options Bias Heatmap"
          subtitle="Color reflects directional evidence — not raw call/put volume alone."
          sectors={heatmap.sectors as Array<{ sector: string; tiles: never[] }>}
          tableFallback={heatmap.table_fallback as never[]}
          legend={heatmap.legend as { size?: string; color?: string; note?: string }}
        />
      )}

      {!loading && tab === "history" && (
        <div className="grid gap-3">
          {history.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
          ))}
          {history.length === 0 && <EmptyState message="No qualified signals persisted yet." />}
        </div>
      )}

      {!loading && tab === "performance" && performance && (
        <div className="rounded-xl border border-border bg-surface/60 p-4 text-sm">
          <p className="font-medium">Outcome engine ready</p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-background/60 p-3 text-xs text-muted">
            {JSON.stringify(performance, null, 2)}
          </pre>
        </div>
      )}

      {!loading && tab === "alerts" && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-background/40 text-xs text-muted">
              <tr>
                <th className="px-3 py-2">Alert</th>
                <th className="px-3 py-2">Enabled</th>
                <th className="px-3 py-2">Threshold</th>
                <th className="px-3 py-2">Cooldown</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={String(a.alert_type)} className="border-t border-border/60">
                  <td className="px-3 py-2">{String(a.alert_type)}</td>
                  <td className="px-3 py-2">{a.enabled ? "On" : "Off"}</td>
                  <td className="px-3 py-2">{a.threshold != null ? String(a.threshold) : "—"}</td>
                  <td className="px-3 py-2">{String(a.cooldown_minutes)}m</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-xs text-muted">
            Simulated alerts are blocked outside development mode.
          </p>
        </div>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
      {message}
    </div>
  );
}
