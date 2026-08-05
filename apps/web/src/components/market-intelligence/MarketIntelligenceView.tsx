"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataStatusBadge, FreshnessLine } from "@/components/market-intelligence/DataStatusBadge";
import { DecisionBrief } from "@/components/market-intelligence/DecisionBrief";
import { EarningsRecommendationCard } from "@/components/market-intelligence/EarningsRecommendationCard";
import { HeatmapPanel } from "@/components/market-intelligence/HeatmapPanel";
import {
  fetchEarningsDesk,
  fetchHistoricalReplay,
  fetchMarketHeatmap,
  fetchMarketWeather,
  fetchOptionsHeatmap,
  fetchPortfolioExitHeatmap,
  fetchSectorRotation,
  fetchSmartMoneyHeatmap,
  type Freshness,
} from "@/lib/market-intelligence-api";
import { buildMarketTodayBrief, exitBand } from "@/lib/market-intelligence-decisions";
import {
  CLIENT_EARNINGS_DESK,
  CLIENT_EXIT_HEATMAP,
  CLIENT_FIXTURE_FRESHNESS,
  CLIENT_HEATMAP,
  CLIENT_SECTOR_ROTATION,
  CLIENT_WEATHER,
} from "@/lib/market-intelligence-fixtures";

const TABS = [
  { id: "heatmap", label: "Stock Heatmap" },
  { id: "earnings", label: "Earnings" },
  { id: "weather", label: "Market Weather" },
  { id: "exit", label: "Exit Guidance" },
  { id: "rotation", label: "Sector Rotation" },
  { id: "options-bias", label: "Options Bias" },
  { id: "smart-money", label: "Smart-Money" },
  { id: "replay", label: "Replay" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function readInitialTab(): TabId {
  if (typeof window === "undefined") return "heatmap";
  const raw = new URLSearchParams(window.location.search).get("tab");
  if (TABS.some((t) => t.id === raw)) return raw as TabId;
  return "heatmap";
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

export function MarketIntelligenceView() {
  const [tab, setTab] = useState<TabId>("heatmap");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(CLIENT_FIXTURE_FRESHNESS);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [rotation, setRotation] = useState<Record<string, unknown>[]>(CLIENT_SECTOR_ROTATION.items);
  const [optionsBias, setOptionsBias] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [exitMap, setExitMap] = useState<Record<string, unknown> | null>(CLIENT_EXIT_HEATMAP);
  const [weather, setWeather] = useState<Record<string, unknown> | null>(CLIENT_WEATHER);
  const [earnings, setEarnings] = useState<Record<string, unknown> | null>(CLIENT_EARNINGS_DESK);
  const [replay, setReplay] = useState<Record<string, unknown> | null>({
    available: false,
    outcome_engine_ready: true,
    message: "Historical replay needs persisted snapshots after migration + API deploy.",
  });
  const [usingFixture, setUsingFixture] = useState(true);

  useEffect(() => {
    setTab(readInitialTab());
  }, []);

  const setTabAndUrl = useCallback((next: TabId) => {
    setTab(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (next === "heatmap") url.searchParams.delete("tab");
      else url.searchParams.set("tab", next);
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const loadDesk = useCallback(async (opts?: { updateFixtureFlag?: boolean }) => {
    const updateFixtureFlag = opts?.updateFixtureFlag !== false;
    try {
      const [weatherData, rotationData, exitData] = await Promise.all([
        fetchMarketWeather(),
        fetchSectorRotation(),
        fetchPortfolioExitHeatmap(),
      ]);
      setWeather(weatherData ?? CLIENT_WEATHER);
      setRotation(rotationData.items ?? CLIENT_SECTOR_ROTATION.items);
      setExitMap(exitData ?? CLIENT_EXIT_HEATMAP);
      setFreshness(
        (weatherData.freshness as Freshness) ??
          rotationData.freshness ??
          CLIENT_FIXTURE_FRESHNESS,
      );
      if (updateFixtureFlag) {
        setUsingFixture(
          weatherData.source === "client_fixture" ||
            rotationData.source === "client_fixture" ||
            exitData.source === "client_fixture",
        );
      }
    } catch {
      if (updateFixtureFlag) setUsingFixture(true);
    }
  }, []);

  const load = useCallback(
    async (active: TabId) => {
      setLoading(true);
      setError(null);
      try {
        if (active === "heatmap") {
          const data = await fetchMarketHeatmap();
          setHeatmap(data ?? CLIENT_HEATMAP);
          setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
          setUsingFixture(data.source === "client_fixture");
          // Warm decision desk without overwriting heatmap live/fixture status
          await loadDesk({ updateFixtureFlag: false });
        } else if (active === "weather" || active === "exit" || active === "rotation") {
          await loadDesk();
        } else if (active === "earnings") {
          const data = await fetchEarningsDesk();
          setEarnings(data ?? CLIENT_EARNINGS_DESK);
          setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
          setUsingFixture(data.source === "client_fixture");
        } else if (active === "options-bias") {
          const bias = await fetchOptionsHeatmap();
          setOptionsBias(bias ?? CLIENT_HEATMAP);
          setFreshness((bias.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
          setUsingFixture(bias.source === "client_fixture");
        } else if (active === "smart-money") {
          const data = await fetchSmartMoneyHeatmap();
          setSmartMoney(data ?? CLIENT_HEATMAP);
          setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
          setUsingFixture(data.source === "client_fixture");
        } else if (active === "replay") {
          const data = await fetchHistoricalReplay();
          setReplay(data);
          setUsingFixture(data.source === "client_fixture");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Load failed");
        setUsingFixture(true);
      } finally {
        setLoading(false);
      }
    },
    [loadDesk],
  );

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const exitTiles = useMemo(
    () => ((exitMap?.tiles_detail as Record<string, unknown>[]) || []),
    [exitMap],
  );

  const brief = useMemo(
    () =>
      buildMarketTodayBrief({
        weather,
        rotation,
        exits: exitTiles,
        usingFixture,
      }),
    [weather, rotation, exitTiles, usingFixture],
  );

  const weatherDetails = (weather?.details as Record<string, unknown> | undefined) ?? {};
  const weatherScore = (weather?.score as Record<string, unknown> | undefined) ?? null;
  const components =
    (weatherScore?.component_values as Record<string, number> | undefined) ?? {};

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Market Intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Stock heatmap, Earnings Intelligence (Yahoo live data), regime context, and swing exit guidance.
          Decision support only — not a forecast or live order routing.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <DataStatusBadge freshness={freshness} />
          <FreshnessLine freshness={freshness} />
          <Link href="/options-intelligence" className="text-xs font-semibold text-accent hover:underline">
            Options Intelligence →
          </Link>
        </div>
        {usingFixture && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            Showing <strong>simulated</strong> fixtures while the API is unreachable or still
            deploying. Use this to learn the decision workflow — not for live risk sizing.
          </div>
        )}
      </header>

      <DecisionBrief eyebrow="Market decision desk" stance={brief.stance} actions={brief.actions} />

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

      {tab === "weather" && weather && (
        <section className="rounded-xl border border-border bg-surface/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-xl font-semibold">{String(weather.label)}</h2>
              <p className="mt-1 text-sm text-muted">
                Confidence {String(weather.confidence)} · Risk {String(weather.risk_level)} · Updated{" "}
                {weather.last_update ? new Date(String(weather.last_update)).toLocaleString() : "—"}
              </p>
            </div>
            <DataStatusBadge freshness={freshness} />
          </div>

          {Object.keys(components).length > 0 && (
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {Object.entries(components).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg border border-border/70 bg-background/30 px-2.5 py-2 text-center"
                >
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">{key}</p>
                  <p className="mt-0.5 text-lg font-semibold">{Number(value).toFixed(0)}</p>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <EvidenceList
              title="Supporting evidence"
              items={(weatherDetails.supporting_evidence as string[]) || []}
            />
            <EvidenceList title="Main risks" items={(weatherDetails.main_risks as string[]) || []} />
            <EvidenceList
              title="Strongest sectors"
              items={(weatherDetails.strongest_sectors as string[]) || []}
            />
            <EvidenceList
              title="Areas to avoid"
              items={(weatherDetails.areas_to_avoid as string[]) || []}
            />
          </div>

          {(Array.isArray(weatherScore?.positive_contributors) ||
            Array.isArray(weatherScore?.negative_contributors)) && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2 text-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-200/80">
                  What helps
                </p>
                <ul className="mt-1 space-y-1 text-muted">
                  {((weatherScore?.positive_contributors as string[]) || []).map((c) => (
                    <li key={c}>◆ {c}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-rose-200/80">
                  What hurts
                </p>
                <ul className="mt-1 space-y-1 text-muted">
                  {((weatherScore?.negative_contributors as string[]) || []).map((c) => (
                    <li key={c}>· {c}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <p className="mt-4 text-xs text-amber-200/80">{String(weatherDetails.disclaimer || "")}</p>
        </section>
      )}

      {tab === "heatmap" && heatmap && (
        <HeatmapPanel
          title="Stock Market Heatmap"
          subtitle={
            heatmap.symbol_count
              ? `${String(heatmap.symbol_count)} liquid names — size ≈ market cap, color = daily % change.`
              : "Size ≈ market cap, color = daily % change from delayed Yahoo/Finnhub quotes."
          }
          sectors={heatmap.sectors as never[]}
          tableFallback={heatmap.table_fallback as never[]}
          legend={
            (heatmap.legend as { size?: string; color?: string; note?: string }) || {
              size: "market_cap",
              color: "daily_return",
              note: "Equity session moves — not options premium.",
            }
          }
          colorBy={String(heatmap.color_by ?? "daily_return")}
        />
      )}

      {tab === "earnings" && earnings && (
        <div className="space-y-5">
          <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sm text-sky-50">
            Real-data desk. Micro-Coattail uses{" "}
            {String((earnings.config as { micro_max_risk_usd?: number } | undefined)?.micro_max_risk_usd ?? 18)}{" "}
            USD max risk (
            {String(
              Math.round(
                Number(
                  (earnings.config as { micro_coattail_fraction?: number } | undefined)
                    ?.micro_coattail_fraction ?? 0.18,
                ) * 100,
              ),
            )}
            % of normal risk). Decision support only — not order routing.
          </div>
          {earnings.disclaimer ? (
            <p className="text-xs text-amber-200/80">{String(earnings.disclaimer)}</p>
          ) : null}

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Upcoming earnings</h2>
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-background/40 text-xs text-muted">
                  <tr>
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Time</th>
                    <th className="px-3 py-2">Phase</th>
                    <th className="px-3 py-2">EPS est.</th>
                  </tr>
                </thead>
                <tbody>
                  {((earnings.upcoming as Record<string, unknown>[]) || []).map((row) => (
                    <tr key={String(row.symbol)} className="border-t border-border/60">
                      <td className="px-3 py-2 font-medium">{String(row.symbol)}</td>
                      <td className="px-3 py-2">{String(row.report_date)}</td>
                      <td className="px-3 py-2">{String(row.release_time)}</td>
                      <td className="px-3 py-2">{String(row.phase)}</td>
                      <td className="px-3 py-2">
                        {row.eps_estimate != null ? String(row.eps_estimate) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Active earnings watchlist</h2>
            <ul className="space-y-1 text-sm text-muted">
              {((earnings.watchlist as Record<string, unknown>[]) || []).map((w) => (
                <li key={`${String(w.symbol)}-${String(w.report_date)}`}>
                  <span className="font-medium text-foreground">{String(w.symbol)}</span> ·{" "}
                  {String(w.phase)} · {String(w.report_date)}
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Pre-earnings opportunities</h2>
            <div className="grid gap-3">
              {((earnings.pre_earnings as Record<string, unknown>[]) || []).map((rec) => (
                <EarningsRecommendationCard
                  key={`pre-${String(rec.symbol)}-${String(rec.recommendation)}`}
                  rec={rec}
                />
              ))}
              {((earnings.pre_earnings as unknown[]) || []).length === 0 && (
                <p className="text-sm text-muted">No pre-earnings setups scored yet.</p>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Post-earnings opportunities</h2>
            <div className="grid gap-3">
              {((earnings.post_earnings as Record<string, unknown>[]) || []).map((rec) => (
                <EarningsRecommendationCard
                  key={`post-${String(rec.symbol)}-${String(rec.recommendation)}`}
                  rec={rec}
                />
              ))}
              {((earnings.post_earnings as unknown[]) || []).length === 0 && (
                <p className="text-sm text-muted">No post-earnings setups scored yet.</p>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Micro-Coattail recommendations</h2>
            <div className="grid gap-3">
              {((earnings.micro_coattails as Record<string, unknown>[]) || []).map((rec) => (
                <EarningsRecommendationCard
                  key={`micro-${String(rec.symbol)}-${String(rec.strategy)}`}
                  rec={rec}
                />
              ))}
              {((earnings.micro_coattails as unknown[]) || []).length === 0 && (
                <p className="text-sm text-muted">No Micro-Coattail edges cleared EV gates.</p>
              )}
            </div>
          </section>

          <details className="rounded-xl border border-border bg-surface/40 p-4">
            <summary className="cursor-pointer text-sm font-semibold">
              Recently reviewed earnings predictions
            </summary>
            <div className="mt-3 grid gap-3">
              {((earnings.recently_reviewed as Record<string, unknown>[]) || []).map((rec) => (
                <EarningsRecommendationCard
                  key={`rev-${String(rec.symbol)}-${String(rec.recommendation)}`}
                  rec={rec}
                />
              ))}
            </div>
          </details>
        </div>
      )}

      {tab === "rotation" && (
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
            </tbody>
          </table>
        </div>
      )}

      {tab === "options-bias" && optionsBias && (
        <HeatmapPanel
          title="Options Bias Heatmap"
          sectors={optionsBias.sectors as never[]}
          tableFallback={optionsBias.table_fallback as never[]}
          legend={optionsBias.legend as never}
          colorBy="options_bias"
        />
      )}

      {tab === "smart-money" && smartMoney && (
        <HeatmapPanel
          title="Smart-Money Heatmap"
          subtitle="Tile size = qualifying premium. Not institutional identity."
          sectors={smartMoney.sectors as never[]}
          tableFallback={smartMoney.table_fallback as never[]}
          legend={smartMoney.legend as never}
          colorBy="options_bias"
        />
      )}

      {tab === "exit" && exitMap && (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            Watchlist / open-signal proxies until a full position ledger exists. Bands: Strong Hold →
            Exit Review.
          </p>
          <div className="grid gap-3">
            {exitTiles.length === 0 && (
              <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted">
                No exit evaluations yet — add names to your watchlist to get Hold / Tighten / Scale
                Out guidance.
              </div>
            )}
            {exitTiles.map((tile) => {
              const urgency = Number(tile.exit_urgency ?? 0);
              return (
                <article key={String(tile.symbol)} className="rounded-xl border border-border bg-surface/60 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="font-semibold">{String(tile.symbol)}</h3>
                      <p className="text-xs text-muted">{String(tile.sector ?? "")}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-accent">{String(tile.action)}</p>
                      <p className="text-[11px] text-muted">
                        {exitBand(urgency)} · urgency {urgency.toFixed(0)}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-sm">{String(tile.primary_reason)}</p>
                  <p className="mt-1 text-xs text-muted">
                    Thesis {String(tile.thesis_status)} · Confidence {String(tile.confidence)}
                    {tile.main_risk ? ` · Watch: ${String(tile.main_risk)}` : ""}
                  </p>
                </article>
              );
            })}
          </div>
          <HeatmapPanel
            title="Exit urgency map"
            subtitle="Color encodes urgency; action labels are color-independent."
            sectors={exitMap.sectors as never[]}
            tableFallback={(exitMap.tiles_detail as never[]) || (exitMap.table_fallback as never[])}
            legend={exitMap.legend as never}
            colorBy="exit_urgency"
          />
        </div>
      )}

      {tab === "replay" && replay && (
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
