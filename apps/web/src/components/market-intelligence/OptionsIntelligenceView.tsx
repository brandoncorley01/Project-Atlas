"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  CLIENT_ALERTS,
  CLIENT_FIXTURE_FRESHNESS,
  CLIENT_FLOW_CARDS,
  CLIENT_HEATMAP,
  CLIENT_PERFORMANCE,
  CLIENT_SMART_MONEY,
} from "@/lib/market-intelligence-fixtures";

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
  const [tab, setTab] = useState<TabId>("flow");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(CLIENT_FIXTURE_FRESHNESS);
  const [disclaimer, setDisclaimer] = useState<string | null>(
    "Loading live provider… showing simulated fixtures until API responds.",
  );
  const [flow, setFlow] = useState<Record<string, unknown>[]>(CLIENT_FLOW_CARDS);
  const [lowPremium, setLowPremium] = useState<Record<string, unknown>[]>([]);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown>[]>(CLIENT_SMART_MONEY);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [history, setHistory] = useState<Record<string, unknown>[]>(CLIENT_FLOW_CARDS);
  const [performance, setPerformance] = useState<Record<string, unknown> | null>(CLIENT_PERFORMANCE);
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>(CLIENT_ALERTS.items);
  const [usingFixture, setUsingFixture] = useState(true);

  const load = useCallback(async (active: TabId) => {
    setLoading(true);
    setError(null);
    try {
      if (active === "flow") {
        const data = await fetchOptionsFlow();
        setFlow(data.items ?? CLIENT_FLOW_CARDS);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "low-premium") {
        const data = await fetchLowPremium();
        setLowPremium(data.items ?? []);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "smart-money") {
        const data = await fetchSmartMoney();
        setSmartMoney(data.items ?? CLIENT_SMART_MONEY);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setDisclaimer(data.disclaimer ?? null);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "heatmap") {
        const data = await fetchOptionsHeatmap();
        setHeatmap(data ?? CLIENT_HEATMAP);
        setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
        setDisclaimer(String(data.disclaimer ?? ""));
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "history") {
        const data = await fetchSignalHistory();
        setHistory(data.items ?? CLIENT_FLOW_CARDS);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "performance") {
        const data = await fetchOptionsPerformance();
        setPerformance(data ?? CLIENT_PERFORMANCE);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "alerts") {
        const data = await fetchAlertSettings();
        setAlerts(data.items ?? CLIENT_ALERTS.items);
        setUsingFixture(data.source === "client_fixture");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
      setUsingFixture(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const lowPremiumCards = useMemo(() => {
    const rows = lowPremium.length
      ? lowPremium
      : CLIENT_FLOW_CARDS.filter((c) => Number(c.current_premium) <= 5).map((card) => ({
          event: {
            underlying: card.ticker,
            expiration: card.expiration,
            strike: card.strike,
            option_type: String(card.contract).includes("PUT") ? "put" : "call",
            contract_price: card.current_premium,
            midpoint: card.current_premium,
            estimated_premium: card.estimated_total_premium,
            contract_volume: card.volume,
            open_interest: card.open_interest,
            volume_oi_ratio: card.volume_oi_ratio,
            data_status: "simulated",
            idempotency_key: card.idempotency_key,
          },
          direction: card.direction,
          score: card.score,
          rank_score: card.unusual_score,
          spread_pct: card.bid_ask_spread_pct,
          review_zone: card.suggested_review_zone,
        }));

    return rows.map((row) => {
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
          idempotency_key: event.idempotency_key,
        } as Record<string, unknown>;
      }
      return row as Record<string, unknown>;
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
            Showing <strong>simulated</strong> fixtures while the Market Intelligence API is
            unreachable or still deploying. Content below is intentional demo data — not live tape.
            Also open{" "}
            <Link href="/market-intelligence" className="underline">
              Market Intelligence
            </Link>
            .
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

      {loading && <p className="text-xs text-muted">Refreshing from API…</p>}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
          {error} — continuing with simulated fixtures.
        </div>
      )}
      {disclaimer && <p className="text-xs text-muted">{disclaimer}</p>}

      {tab === "flow" && (
        <div className="grid gap-3">
          {flow.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
          ))}
        </div>
      )}

      {tab === "low-premium" && (
        <div className="grid gap-3">
          {lowPremiumCards.map((card, idx) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? idx)} card={card} />
          ))}
        </div>
      )}

      {tab === "smart-money" && (
        <div className="grid gap-3">
          {smartMoney.map((row) => (
            <article key={String(row.underlying)} className="rounded-xl border border-border bg-surface/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">{String(row.underlying)}</h3>
                <DataStatusBadge status={String(row.data_status ?? "simulated")} />
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
              <p className="mt-2 text-[11px] text-amber-200/80">{String(row.disclaimer ?? "")}</p>
            </article>
          ))}
        </div>
      )}

      {tab === "heatmap" && heatmap && (
        <HeatmapPanel
          title="Options Bias Heatmap"
          subtitle="Color reflects directional evidence — not raw call/put volume alone."
          sectors={heatmap.sectors as Array<{ sector: string; tiles: never[] }>}
          tableFallback={heatmap.table_fallback as never[]}
          legend={heatmap.legend as { size?: string; color?: string; note?: string }}
        />
      )}

      {tab === "history" && (
        <div className="grid gap-3">
          {history.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
          ))}
        </div>
      )}

      {tab === "performance" && performance && (
        <div className="rounded-xl border border-border bg-surface/60 p-4 text-sm">
          <p className="font-medium">Outcome engine ready</p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-background/60 p-3 text-xs text-muted">
            {JSON.stringify(performance, null, 2)}
          </pre>
        </div>
      )}

      {tab === "alerts" && (
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
        </div>
      )}
    </div>
  );
}
