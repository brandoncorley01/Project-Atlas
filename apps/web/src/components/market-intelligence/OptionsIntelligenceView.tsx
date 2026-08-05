"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataStatusBadge, FreshnessLine } from "@/components/market-intelligence/DataStatusBadge";
import { DecisionBrief } from "@/components/market-intelligence/DecisionBrief";
import { HeatmapPanel } from "@/components/market-intelligence/HeatmapPanel";
import { OptionsTradeCard } from "@/components/market-intelligence/OptionsTradeCard";
import {
  fetchAlertSettings,
  fetchCongressTrades,
  fetchDarkPool,
  fetchLowPremium,
  fetchOptionsFlow,
  fetchOptionsHeatmap,
  fetchOptionsPerformance,
  fetchSignalHistory,
  fetchSmartMoney,
  type Freshness,
} from "@/lib/market-intelligence-api";
import { buildOptionsTodayBrief } from "@/lib/market-intelligence-decisions";
import {
  CLIENT_ALERTS,
  CLIENT_CONGRESS_TRADES,
  CLIENT_DARK_POOL,
  CLIENT_FIXTURE_FRESHNESS,
  CLIENT_FLOW_CARDS,
  CLIENT_HEATMAP,
  CLIENT_PERFORMANCE,
  CLIENT_SMART_MONEY,
} from "@/lib/market-intelligence-fixtures";

const TABS = [
  { id: "today", label: "Today" },
  { id: "flow", label: "Flow Tracker" },
  { id: "dark-pool", label: "Dark Pool" },
  { id: "congress", label: "Politician Trades" },
  { id: "low-premium", label: "Low-Premium" },
  { id: "smart-money", label: "Smart-Money" },
  { id: "heatmap", label: "Options Heatmap" },
  { id: "history", label: "History" },
  { id: "performance", label: "Performance" },
  { id: "alerts", label: "Alerts" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function readInitialTab(): TabId {
  if (typeof window === "undefined") return "today";
  const raw = new URLSearchParams(window.location.search).get("tab");
  if (TABS.some((t) => t.id === raw)) return raw as TabId;
  return "today";
}

export function OptionsIntelligenceView() {
  const [tab, setTab] = useState<TabId>("today");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(CLIENT_FIXTURE_FRESHNESS);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [flow, setFlow] = useState<Record<string, unknown>[]>(CLIENT_FLOW_CARDS);
  const [lowPremium, setLowPremium] = useState<Record<string, unknown>[]>([]);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown>[]>(CLIENT_SMART_MONEY);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [history, setHistory] = useState<Record<string, unknown>[]>(CLIENT_FLOW_CARDS);
  const [performance, setPerformance] = useState<Record<string, unknown> | null>(CLIENT_PERFORMANCE);
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>(CLIENT_ALERTS.items);
  const [darkPool, setDarkPool] = useState<Record<string, unknown>[]>(CLIENT_DARK_POOL);
  const [darkPoolMeta, setDarkPoolMeta] = useState<{ week_start?: string | null; disclaimer?: string }>({});
  const [congress, setCongress] = useState<Record<string, unknown>[]>(CLIENT_CONGRESS_TRADES);
  const [congressDisclaimer, setCongressDisclaimer] = useState<string | null>(null);
  const [usingFixture, setUsingFixture] = useState(true);

  useEffect(() => {
    setTab(readInitialTab());
  }, []);

  const setTabAndUrl = useCallback((next: TabId) => {
    setTab(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (next === "today") url.searchParams.delete("tab");
      else url.searchParams.set("tab", next);
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const loadDesk = useCallback(async () => {
    try {
      const [flowData, smartData, perfData] = await Promise.all([
        fetchOptionsFlow(),
        fetchSmartMoney(),
        fetchOptionsPerformance(),
      ]);
      setFlow(flowData.items ?? CLIENT_FLOW_CARDS);
      setSmartMoney(smartData.items ?? CLIENT_SMART_MONEY);
      setPerformance(perfData ?? CLIENT_PERFORMANCE);
      setFreshness(flowData.freshness ?? CLIENT_FIXTURE_FRESHNESS);
      setDisclaimer(flowData.disclaimer ?? null);
      setUsingFixture(
        flowData.source === "client_fixture" ||
          smartData.source === "client_fixture" ||
          perfData.source === "client_fixture",
      );
    } catch {
      setUsingFixture(true);
    }
  }, []);

  const load = useCallback(async (active: TabId) => {
    setLoading(true);
    setError(null);
    try {
      if (active === "today") {
        await loadDesk();
      } else if (active === "flow") {
        const data = await fetchOptionsFlow();
        setFlow(data.items ?? CLIENT_FLOW_CARDS);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setDisclaimer(
          data.disclaimer ??
            "Options Flow Tracker monitors unusual chain activity (delayed Yahoo-derived unusualness when live tape is unavailable). Large prints may be hedges or spreads.",
        );
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "dark-pool") {
        const data = await fetchDarkPool();
        setDarkPool(data.items ?? []);
        setDarkPoolMeta({
          week_start: data.week_start,
          disclaimer: data.disclaimer,
        });
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
        setUsingFixture(data.source === "client_fixture");
      } else if (active === "congress") {
        const data = await fetchCongressTrades();
        setCongress(data.items ?? []);
        setCongressDisclaimer(data.disclaimer ?? null);
        setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
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
  }, [loadDesk]);

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const brief = useMemo(
    () => buildOptionsTodayBrief({ flow, smartMoney, performance, usingFixture }),
    [flow, smartMoney, performance, usingFixture],
  );

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

  const perfSummary = (performance?.summary as Record<string, unknown> | undefined) ?? {};

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Options Intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Options Flow Tracker, FINRA dark-pool volume, and STOCK Act politician disclosures —
          decide what to review, size, watch, or pass. Unusual activity does not prove intent.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <DataStatusBadge freshness={freshness} />
          <FreshnessLine freshness={freshness} />
          <Link href="/market-intelligence" className="text-xs font-semibold text-accent hover:underline">
            Market Intelligence →
          </Link>
          <Link href="/options" className="text-xs font-semibold text-accent hover:underline">
            Options board →
          </Link>
        </div>
        {usingFixture && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            Showing <strong>simulated</strong> fixtures while the API is unreachable or still
            deploying. Learn the workflow here — do not treat this as live tape.
          </div>
        )}
      </header>

      <DecisionBrief eyebrow="Options decision desk" stance={brief.stance} actions={brief.actions} />

      <div className="flex gap-1 overflow-x-auto pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTabAndUrl(t.id)}
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

      {loading && <p className="text-xs text-muted">Refreshing…</p>}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
          {error} — continuing with simulated fixtures.
        </div>
      )}
      {disclaimer && <p className="text-xs text-muted">{disclaimer}</p>}

      {tab === "today" && (
        <div className="space-y-4" id="flow-board">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Top prints to decide on</h2>
            <p className="mt-1 text-xs text-muted">
              Ranked by unusual score — each card tells you take, size small, watch, or pass.
            </p>
          </div>
          <div className="grid gap-3">
            {brief.topCards.map((card) => (
              <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
            ))}
          </div>
          {smartMoney[0] && (
            <article className="rounded-xl border border-border bg-surface/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">{String(smartMoney[0].underlying)}</h3>
                <button
                  type="button"
                  onClick={() => setTabAndUrl("smart-money")}
                  className="text-xs font-semibold text-accent hover:underline"
                >
                  Full watchlist →
                </button>
              </div>
              <p className="mt-1 text-sm">{String(smartMoney[0].label)}</p>
              <p className="mt-2 text-xs text-muted">
                Score {String(smartMoney[0].unusual_score)} · Confidence{" "}
                {String(smartMoney[0].confidence)} · not institutional identity
              </p>
            </article>
          )}
        </div>
      )}

      {tab === "flow" && (
        <div className="grid gap-3" id="flow-board">
          <p className="text-sm text-muted">
            Flow Tracker ranks large / unusual options activity so you can see where size is leaning.
            When the live tape vendor is not configured, Atlas uses delayed Yahoo chain unusualness —
            never labelled as live OPRA prints.
          </p>
          {flow.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} />
          ))}
        </div>
      )}

      {tab === "dark-pool" && (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            Official FINRA ATS / OTC transparency — aggregated off-exchange (dark pool) share volume
            by symbol for the latest published week. Multi-week regulatory delay. Not live prints and
            not institutional identity.
          </p>
          {darkPoolMeta.week_start && (
            <p className="text-xs text-muted">Week starting {String(darkPoolMeta.week_start)}</p>
          )}
          {darkPoolMeta.disclaimer && (
            <p className="text-xs text-amber-200/80">{darkPoolMeta.disclaimer}</p>
          )}
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-background/40 text-xs text-muted">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">ATS shares</th>
                  <th className="px-3 py-2">Notional</th>
                  <th className="px-3 py-2">Trades</th>
                  <th className="px-3 py-2">vs prior week</th>
                  <th className="px-3 py-2">Tag</th>
                </tr>
              </thead>
              <tbody>
                {darkPool.map((row) => (
                  <tr key={String(row.symbol)} className="border-t border-border/60">
                    <td className="px-3 py-2 font-medium">{String(row.symbol)}</td>
                    <td className="px-3 py-2">{Number(row.ats_shares ?? 0).toLocaleString()}</td>
                    <td className="px-3 py-2">
                      {row.ats_notional != null
                        ? `$${Number(row.ats_notional).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : "—"}
                    </td>
                    <td className="px-3 py-2">{Number(row.ats_trades ?? 0).toLocaleString()}</td>
                    <td className="px-3 py-2">
                      {row.vs_prior_week != null ? `${Number(row.vs_prior_week).toFixed(2)}×` : "—"}
                    </td>
                    <td className="px-3 py-2 capitalize">{String(row.activity_tag ?? "—")}</td>
                  </tr>
                ))}
                {darkPool.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted">
                      No ATS rows available.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "congress" && (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            Public STOCK Act disclosures from the U.S. House Clerk (Periodic Transaction Reports).
            Filings can lag the trade by up to ~45 days. Transparency log only — not investment advice.
          </p>
          {congressDisclaimer && <p className="text-xs text-amber-200/80">{congressDisclaimer}</p>}
          <div className="grid gap-3">
            {congress.map((row, idx) => (
              <article
                key={`${String(row.doc_id ?? row.member)}-${String(row.ticker ?? idx)}`}
                className="rounded-xl border border-border bg-surface/60 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold text-foreground">
                      {String(row.member ?? "Member")}
                      {row.ticker ? (
                        <span className="ml-2 text-accent">{String(row.ticker)}</span>
                      ) : null}
                    </h3>
                    <p className="text-xs text-muted">
                      {String(row.chamber ?? "House")}
                      {row.state_district ? ` · ${String(row.state_district)}` : ""}
                      {row.transaction_type ? ` · ${String(row.transaction_type)}` : ""}
                    </p>
                  </div>
                  <DataStatusBadge status={String(row.data_status ?? "delayed")} />
                </div>
                <p className="mt-2 text-sm text-foreground/90">
                  {row.asset_name ? String(row.asset_name) : "PTR filing"}
                  {row.amount ? ` · ${String(row.amount)}` : ""}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Trade {String(row.transaction_date ?? "—")} · Filed {String(row.filing_date ?? "—")}
                </p>
                {row.ptr_url ? (
                  <a
                    href={String(row.ptr_url)}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
                  >
                    Official PTR PDF →
                  </a>
                ) : null}
                {row.note ? <p className="mt-2 text-[11px] text-amber-200/80">{String(row.note)}</p> : null}
              </article>
            ))}
            {congress.length === 0 && (
              <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted">
                No recent House PTR disclosures parsed yet.
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "low-premium" && (
        <div className="grid gap-3">
          <p className="text-xs text-muted">
            Affordable contracts only — cheap alone does not qualify; unusualness must confirm.
          </p>
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
          colorBy="options_bias"
        />
      )}

      {tab === "history" && (
        <div className="grid gap-3">
          {history.map((card) => (
            <OptionsTradeCard key={String(card.idempotency_key ?? card.contract)} card={card} compact />
          ))}
        </div>
      )}

      {tab === "performance" && performance && (
        <section className="rounded-xl border border-border bg-surface/60 p-4 sm:p-5">
          <h2 className="text-base font-semibold">Options intel track record</h2>
          <p className="mt-1 text-sm text-muted">
            {String(perfSummary.note ?? performance.disclaimer ?? "Outcome tracking for intel signals.")}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-border/70 bg-background/30 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">Signals tracked</p>
              <p className="mt-1 text-2xl font-semibold">{String(perfSummary.signals_tracked ?? 0)}</p>
            </div>
            <div className="rounded-lg border border-border/70 bg-background/30 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">Hit rate</p>
              <p className="mt-1 text-2xl font-semibold">
                {perfSummary.hit_rate != null ? `${String(perfSummary.hit_rate)}%` : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-border/70 bg-background/30 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">Avg return</p>
              <p className="mt-1 text-2xl font-semibold">
                {perfSummary.avg_return != null ? `${String(perfSummary.avg_return)}%` : "—"}
              </p>
            </div>
          </div>
          <p className="mt-4 text-xs text-amber-200/80">{String(performance.disclaimer ?? "")}</p>
          <Link href="/performance" className="mt-3 inline-block text-xs font-semibold text-accent hover:underline">
            Full Atlas learning loop →
          </Link>
        </section>
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
                  <td className="px-3 py-2">{String(a.alert_type).replaceAll("_", " ")}</td>
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
