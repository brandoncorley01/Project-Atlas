"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { DataStatusBadge, FreshnessLine } from "@/components/market-intelligence/DataStatusBadge";
import { HeatmapPanel } from "@/components/market-intelligence/HeatmapPanel";
import {
  fetchHistoricalReplay,
  fetchMarketHeatmap,
  fetchMarketWeather,
  fetchOptionsHeatmap,
  fetchPortfolioExitHeatmap,
  fetchSectorRotation,
  fetchSmartMoneyHeatmap,
  type Freshness,
} from "@/lib/market-intelligence-api";

const TABS = [
  { id: "heatmap", label: "Market Heatmap" },
  { id: "rotation", label: "Sector Rotation" },
  { id: "options-bias", label: "Options Bias" },
  { id: "smart-money", label: "Smart-Money Heatmap" },
  { id: "exit", label: "Portfolio Exit Heatmap" },
  { id: "weather", label: "Market Weather" },
  { id: "replay", label: "Historical Replay" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function MarketIntelligenceView() {
  const search = useSearchParams();
  const initial = (search.get("tab") as TabId) || "weather";
  const [tab, setTab] = useState<TabId>(TABS.some((t) => t.id === initial) ? initial : "weather");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(null);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(null);
  const [rotation, setRotation] = useState<Record<string, unknown>[]>([]);
  const [optionsBias, setOptionsBias] = useState<Record<string, unknown> | null>(null);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown> | null>(null);
  const [exitMap, setExitMap] = useState<Record<string, unknown> | null>(null);
  const [weather, setWeather] = useState<Record<string, unknown> | null>(null);
  const [replay, setReplay] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async (active: TabId) => {
    setLoading(true);
    setError(null);
    try {
      if (active === "heatmap") {
        const data = await fetchMarketHeatmap();
        if (!data) throw new Error("Could not load market heatmap");
        setHeatmap(data);
        setFreshness((data.freshness as Freshness) ?? null);
      } else if (active === "rotation") {
        const data = await fetchSectorRotation();
        if (!data) throw new Error("Could not load sector rotation");
        setRotation(data.items ?? []);
        setFreshness(data.freshness ?? null);
      } else if (active === "options-bias") {
        const bias = await fetchOptionsHeatmap();
        if (!bias) throw new Error("Could not load options bias heatmap");
        setOptionsBias(bias);
        setFreshness((bias.freshness as Freshness) ?? null);
      } else if (active === "smart-money") {
        const data = await fetchSmartMoneyHeatmap();
        if (!data) throw new Error("Could not load smart-money heatmap");
        setSmartMoney(data);
        setFreshness((data.freshness as Freshness) ?? null);
      } else if (active === "exit") {
        const data = await fetchPortfolioExitHeatmap();
        if (!data) throw new Error("Could not load portfolio exit heatmap");
        setExitMap(data);
        setFreshness((data.freshness as Freshness) ?? null);
      } else if (active === "weather") {
        const data = await fetchMarketWeather();
        if (!data) throw new Error("Could not load market weather");
        setWeather(data);
        setFreshness((data.freshness as Freshness) ?? null);
      } else if (active === "replay") {
        const data = await fetchHistoricalReplay();
        if (!data) throw new Error("Could not load replay status");
        setReplay(data);
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

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Market Intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Heatmaps, sector rotation, Market Weather, and swing-trade exit guidance. Describes recent
          conditions — not a guarantee of future movement. Exit guidance is decision support only.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <DataStatusBadge freshness={freshness} />
          <FreshnessLine freshness={freshness} />
        </div>
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

      {!loading && tab === "heatmap" && heatmap && (
        <HeatmapPanel
          title="Market Heatmap"
          subtitle="Drill into Options Intelligence from notable names on your watchlist flow."
          sectors={heatmap.sectors as never[]}
          tableFallback={heatmap.table_fallback as never[]}
          legend={heatmap.legend as never}
        />
      )}

      {!loading && tab === "rotation" && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-background/40 text-xs text-muted">
              <tr>
                <th className="px-3 py-2">Sector</th>
                <th className="px-3 py-2">Class</th>
                <th className="px-3 py-2">Rel return</th>
                <th className="px-3 py-2">Options bias</th>
                <th className="px-3 py-2">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rotation.map((row) => (
                <tr key={String(row.sector)} className="border-t border-border/60 align-top">
                  <td className="px-3 py-2 font-medium">{String(row.sector)}</td>
                  <td className="px-3 py-2">{String(row.classification)}</td>
                  <td className="px-3 py-2">{String(row.relative_return)}</td>
                  <td className="px-3 py-2">{String(row.options_bias)}</td>
                  <td className="px-3 py-2 text-xs text-muted">
                    {(Array.isArray(row.evidence) ? (row.evidence as string[]) : []).join(" · ")}
                  </td>
                </tr>
              ))}
              {rotation.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-muted">
                    Insufficient sector data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && tab === "options-bias" && optionsBias && (
        <HeatmapPanel
          title="Options Bias Heatmap"
          sectors={optionsBias.sectors as never[]}
          tableFallback={optionsBias.table_fallback as never[]}
          legend={optionsBias.legend as never}
        />
      )}

      {!loading && tab === "smart-money" && smartMoney && (
        <HeatmapPanel
          title="Smart-Money Heatmap"
          subtitle="Tile size = qualifying premium. Not institutional identity."
          sectors={smartMoney.sectors as never[]}
          tableFallback={smartMoney.table_fallback as never[]}
          legend={smartMoney.legend as never}
        />
      )}

      {!loading && tab === "exit" && exitMap && (
        <div className="space-y-4">
          <HeatmapPanel
            title="Portfolio Exit Heatmap"
            subtitle="Watchlist / open-signal proxies until a full position ledger exists."
            sectors={exitMap.sectors as never[]}
            tableFallback={(exitMap.tiles_detail as never[]) || (exitMap.table_fallback as never[])}
            legend={exitMap.legend as never}
          />
          <div className="grid gap-3">
            {((exitMap.tiles_detail as Record<string, unknown>[]) || []).map((tile) => (
              <article key={String(tile.symbol)} className="rounded-xl border border-border bg-surface/60 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">{String(tile.symbol)}</h3>
                  <span className="text-xs text-accent">{String(tile.action)}</span>
                </div>
                <p className="mt-2 text-sm">{String(tile.primary_reason)}</p>
                <p className="mt-1 text-xs text-muted">
                  Exit urgency {String(tile.exit_urgency)} · Thesis {String(tile.thesis_status)} ·
                  Confidence {String(tile.confidence)}
                </p>
              </article>
            ))}
          </div>
        </div>
      )}

      {!loading && tab === "weather" && weather && (
        <section className="rounded-xl border border-border bg-surface/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xl font-semibold">{String(weather.label)}</h2>
            <DataStatusBadge freshness={freshness} />
          </div>
          <p className="mt-2 text-sm text-muted">
            Confidence {String(weather.confidence)} · Risk {String(weather.risk_level)} · Updated{" "}
            {weather.last_update ? new Date(String(weather.last_update)).toLocaleString() : "—"}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <EvidenceList
              title="Supporting evidence"
              items={((weather.details as { supporting_evidence?: string[] })?.supporting_evidence) || []}
            />
            <EvidenceList
              title="Main risks"
              items={((weather.details as { main_risks?: string[] })?.main_risks) || []}
            />
            <EvidenceList
              title="Strongest sectors"
              items={((weather.details as { strongest_sectors?: string[] })?.strongest_sectors) || []}
            />
            <EvidenceList
              title="Areas to avoid"
              items={((weather.details as { areas_to_avoid?: string[] })?.areas_to_avoid) || []}
            />
          </div>
          <p className="mt-4 text-xs text-amber-200/80">
            {String((weather.details as { disclaimer?: string })?.disclaimer || "")}
          </p>
          {weather.score != null ? (
            <pre className="mt-3 overflow-x-auto rounded-lg bg-background/50 p-3 text-[11px] text-muted">
              {JSON.stringify(weather.score, null, 2)}
            </pre>
          ) : null}
        </section>
      )}

      {!loading && tab === "replay" && replay && (
        <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted">
          <p className="font-medium text-foreground">Historical Replay</p>
          <p className="mt-2">{String(replay.message)}</p>
          <p className="mt-2 text-xs">
            Outcome engine ready: {String(replay.outcome_engine_ready)} · Available:{" "}
            {String(replay.available)}
          </p>
        </div>
      )}
    </div>
  );
}

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
      <ul className="mt-1 space-y-1 text-sm">
        {items.length === 0 && <li className="text-muted">—</li>}
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}
