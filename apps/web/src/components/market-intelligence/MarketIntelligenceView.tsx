"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DataStatusBadge, FreshnessLine } from "@/components/market-intelligence/DataStatusBadge";
import { HeatmapPanel } from "@/components/market-intelligence/HeatmapPanel";
import { ScoreFactors } from "@/components/market-intelligence/ScoreFactors";
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
import {
  CLIENT_EXIT_HEATMAP,
  CLIENT_FIXTURE_FRESHNESS,
  CLIENT_HEATMAP,
  CLIENT_SECTOR_ROTATION,
  CLIENT_WEATHER,
} from "@/lib/market-intelligence-fixtures";

const TABS = [
  { id: "brief", label: "Decision brief" },
  { id: "heatmap", label: "Market Heatmap" },
  { id: "rotation", label: "Sector Rotation" },
  { id: "options-bias", label: "Options Bias" },
  { id: "smart-money", label: "Smart-Money Heatmap" },
  { id: "exit", label: "Exit Guidance" },
  { id: "weather", label: "Weather detail" },
  { id: "replay", label: "Historical Replay" },
] as const;

type TabId = (typeof TABS)[number]["id"];

type WeatherScore = {
  final_score?: number;
  confidence?: number;
  component_values?: Record<string, number>;
  positive_contributors?: string[];
  negative_contributors?: string[];
  score_version?: string;
};

type WeatherDetails = {
  supporting_evidence?: string[];
  main_risks?: string[];
  strongest_sectors?: string[];
  areas_to_avoid?: string[];
  favorable_environments?: string[];
  disclaimer?: string;
};

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

export function MarketIntelligenceView() {
  const [tab, setTab] = useState<TabId>("brief");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<Freshness | null>(CLIENT_FIXTURE_FRESHNESS);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [rotation, setRotation] = useState<Record<string, unknown>[]>(CLIENT_SECTOR_ROTATION.items);
  const [optionsBias, setOptionsBias] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [smartMoney, setSmartMoney] = useState<Record<string, unknown> | null>(CLIENT_HEATMAP);
  const [exitMap, setExitMap] = useState<Record<string, unknown> | null>(CLIENT_EXIT_HEATMAP);
  const [weather, setWeather] = useState<Record<string, unknown> | null>(CLIENT_WEATHER);
  const [replay, setReplay] = useState<Record<string, unknown> | null>({
    available: false,
    outcome_engine_ready: true,
    message: "Historical replay needs persisted snapshots after migration + API deploy.",
  });
  const [usingFixture, setUsingFixture] = useState(true);

  const applyWeather = useCallback((data: Record<string, unknown> & { source?: string }) => {
    setWeather(data ?? CLIENT_WEATHER);
    setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
    setUsingFixture(data.source === "client_fixture");
  }, []);

  const load = useCallback(
    async (active: TabId) => {
      setLoading(true);
      setError(null);
      try {
        if (active === "brief" || active === "weather") {
          const [w, rot, exit] = await Promise.all([
            fetchMarketWeather(),
            fetchSectorRotation(),
            fetchPortfolioExitHeatmap(),
          ]);
          applyWeather(w);
          setRotation(rot.items ?? CLIENT_SECTOR_ROTATION.items);
          setExitMap(exit ?? CLIENT_EXIT_HEATMAP);
          if (active === "brief") {
            setUsingFixture(
              w.source === "client_fixture" ||
                rot.source === "client_fixture" ||
                exit.source === "client_fixture",
            );
          }
        } else if (active === "heatmap") {
          const data = await fetchMarketHeatmap();
          setHeatmap(data ?? CLIENT_HEATMAP);
          setFreshness((data.freshness as Freshness) ?? CLIENT_FIXTURE_FRESHNESS);
          setUsingFixture(data.source === "client_fixture");
        } else if (active === "rotation") {
          const data = await fetchSectorRotation();
          setRotation(data.items ?? CLIENT_SECTOR_ROTATION.items);
          setFreshness(data.freshness ?? CLIENT_FIXTURE_FRESHNESS);
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
        } else if (active === "exit") {
          const data = await fetchPortfolioExitHeatmap();
          setExitMap(data ?? CLIENT_EXIT_HEATMAP);
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
    [applyWeather],
  );

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const details = (weather?.details as WeatherDetails | undefined) ?? {};
  const score = (weather?.score as WeatherScore | undefined) ?? {};
  const doNow = asStringList(weather?.do_now);
  const avoidNow = asStringList(weather?.avoid_now);
  const exitTiles =
    (exitMap?.tiles_detail as Record<string, unknown>[]) ||
    (exitMap?.table_fallback as Record<string, unknown>[]) ||
    [];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Market Intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Decision-first market weather, sector posture, options heat, and swing exit actions —
          written for what to do next, not raw model dumps.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <DataStatusBadge freshness={freshness} />
          <FreshnessLine freshness={freshness} />
        </div>
        {usingFixture && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            Showing <strong>simulated</strong> fixtures while the Market Intelligence API is
            unreachable or still deploying. Also see{" "}
            <Link href="/options-intelligence" className="underline">
              Options Intelligence
            </Link>
            .
          </div>
        )}
      </header>

      {/* Always-visible decision header */}
      {weather && (
        <section className="overflow-hidden rounded-2xl border border-border bg-surface/80">
          <div className="grid gap-5 p-5 lg:grid-cols-[1.35fr_1fr]">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-accent/20 px-3 py-1 text-xs font-semibold text-accent">
                  {String(weather.posture || weather.label || "Market posture")}
                </span>
                <span className="text-xs text-muted">
                  Confidence {String(weather.confidence)} · Risk {String(weather.risk_level)}
                </span>
              </div>
              <p className="mt-3 text-lg font-semibold leading-snug text-foreground sm:text-xl">
                {String(weather.takeaway || weather.label || "Market posture unavailable.")}
              </p>
              {details.favorable_environments?.length ? (
                <p className="mt-2 text-sm text-muted">
                  Best fits: {details.favorable_environments.join(" · ")}
                </p>
              ) : null}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              <ActionBox title="Do now" tone="good" items={doNow.length ? doNow : ["Favor setups with clear invalidation."]} />
              <ActionBox title="Avoid now" tone="warn" items={avoidNow.length ? avoidNow : ["Avoid forcing size without confirmation."]} />
            </div>
          </div>
        </section>
      )}

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

      {tab === "brief" && (
        <div className="space-y-6">
          <section>
            <h2 className="text-lg font-semibold">Sector posture</h2>
            <p className="mt-1 text-sm text-muted">
              Where to hunt ideas vs stand aside — guidance, not a trade ticket.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {rotation.map((row) => (
                <article key={String(row.sector)} className="rounded-xl border border-border bg-surface/60 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold">{String(row.sector)}</p>
                      <p className="mt-0.5 text-xs text-muted">{String(row.classification)}</p>
                    </div>
                    <span className="rounded-full bg-background/70 px-2 py-0.5 text-[11px] font-medium">
                      {String(row.posture || "Review")}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-foreground/90">
                    {String(row.guidance || "Stay selective until leadership clarifies.")}
                  </p>
                  <ul className="mt-2 space-y-1 text-xs text-muted">
                    {asStringList(row.evidence)
                      .slice(0, 3)
                      .map((e) => (
                        <li key={e}>• {e}</li>
                      ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          <section>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold">Priority exits</h2>
                <p className="mt-1 text-sm text-muted">Highest-urgency swing actions from exit intelligence.</p>
              </div>
              <button
                type="button"
                onClick={() => setTab("exit")}
                className="text-sm font-medium text-accent hover:underline"
              >
                View all exits →
              </button>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {exitTiles.slice(0, 4).map((tile) => (
                <ExitCard key={String(tile.symbol)} tile={tile} />
              ))}
              {exitTiles.length === 0 && (
                <p className="text-sm text-muted">No exit actions ranked yet.</p>
              )}
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface/40 p-4">
            <h2 className="text-sm font-semibold">How to use this brief</h2>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted">
              <li>Start with posture and Do / Avoid — that sets risk budget for the session.</li>
              <li>Scan sector posture for where to hunt ideas (or stay away).</li>
              <li>Open Options Bias for flow confirmation before sizing.</li>
              <li>Work Priority exits against your actual holdings and plan.</li>
            </ol>
          </section>
        </div>
      )}

      {tab === "heatmap" && heatmap && (
        <HeatmapPanel
          title="Market Heatmap"
          subtitle="Drill into Options Intelligence from notable names."
          meaning={String(heatmap.meaning || CLIENT_HEATMAP.meaning)}
          sectors={heatmap.sectors as never[]}
          tableFallback={heatmap.table_fallback as never[]}
          legend={heatmap.legend as never}
        />
      )}

      {tab === "rotation" && (
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Sector rotation</h2>
            <p className="mt-1 text-sm text-muted">
              Relative strength plus options lean — use posture and guidance before scanning names.
            </p>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {rotation.map((row) => (
              <article key={String(row.sector)} className="rounded-xl border border-border bg-surface/60 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">{String(row.sector)}</h3>
                  <span className="text-xs text-accent">{String(row.classification)}</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  Rel return {String(row.relative_return)} · Options bias {String(row.options_bias)} ·{" "}
                  {String(row.member_count)} names in focus
                </p>
                <p className="mt-3 text-sm font-medium text-foreground">{String(row.posture)}</p>
                <p className="mt-1 text-sm text-muted">{String(row.guidance)}</p>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {asStringList(row.evidence).map((e) => (
                    <li key={e}>• {e}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      )}

      {tab === "options-bias" && optionsBias && (
        <HeatmapPanel
          title="Options Bias Heatmap"
          meaning={String(optionsBias.meaning || CLIENT_HEATMAP.meaning)}
          sectors={optionsBias.sectors as never[]}
          tableFallback={optionsBias.table_fallback as never[]}
          legend={optionsBias.legend as never}
        />
      )}

      {tab === "smart-money" && smartMoney && (
        <HeatmapPanel
          title="Smart-Money Heatmap"
          subtitle="Tile size = qualifying premium. Not institutional identity."
          meaning="Concentrated premium can be hedges or spreads — treat as a watchlist cue, not proof of smart money."
          sectors={smartMoney.sectors as never[]}
          tableFallback={smartMoney.table_fallback as never[]}
          legend={smartMoney.legend as never}
        />
      )}

      {tab === "exit" && exitMap && (
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Swing exit guidance</h2>
            <p className="mt-1 text-sm text-muted">
              Action, urgency, and invalidation — written for decisions, not model dumps.
            </p>
          </div>
          <HeatmapPanel
            title="Exit urgency map"
            subtitle="Higher urgency means review risk sooner — not an automatic sell."
            meaning={String(exitMap.meaning || CLIENT_EXIT_HEATMAP.meaning)}
            sectors={exitMap.sectors as never[]}
            tableFallback={(exitMap.tiles_detail as never[]) || (exitMap.table_fallback as never[])}
            legend={exitMap.legend as never}
            linkModule="stocks"
          />
          <div className="grid gap-3 lg:grid-cols-2">
            {exitTiles.map((tile) => (
              <ExitCard key={`full-${String(tile.symbol)}`} tile={tile} />
            ))}
          </div>
        </div>
      )}

      {tab === "weather" && weather && (
        <section className="space-y-4 rounded-xl border border-border bg-surface/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xl font-semibold">{String(weather.label)}</h2>
            <DataStatusBadge freshness={freshness} />
          </div>
          <p className="text-sm text-muted">
            Confidence {String(weather.confidence)} · Risk {String(weather.risk_level)} · Updated{" "}
            {weather.last_update ? new Date(String(weather.last_update)).toLocaleString() : "—"}
          </p>
          {weather.takeaway ? (
            <p className="text-sm leading-relaxed text-foreground/90">{String(weather.takeaway)}</p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <EvidenceList title="Supporting evidence" items={details.supporting_evidence || []} />
            <EvidenceList title="Main risks" items={details.main_risks || []} />
            <EvidenceList title="Strongest sectors" items={details.strongest_sectors || []} />
            <EvidenceList title="Areas to avoid" items={details.areas_to_avoid || []} />
          </div>
          <ScoreFactors
            title="What’s driving the weather score"
            positives={score.positive_contributors}
            negatives={score.negative_contributors}
            components={score.component_values}
          />
          {score.score_version ? (
            <p className="text-xs text-muted">Model {String(score.score_version)}</p>
          ) : null}
          <p className="text-xs text-amber-200/80">{String(details.disclaimer || "")}</p>
        </section>
      )}

      {tab === "replay" && replay && (
        <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted">
          <p className="font-medium text-foreground">Historical Replay</p>
          <p className="mt-2">{String(replay.message)}</p>
          <p className="mt-2 text-xs">
            Outcome engine ready: {replay.outcome_engine_ready ? "Yes" : "No"} · Available:{" "}
            {replay.available ? "Yes" : "Not yet"}
          </p>
        </div>
      )}
    </div>
  );
}

function ActionBox({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "good" | "warn";
}) {
  const color = tone === "good" ? "text-emerald-300" : "text-amber-200";
  return (
    <div className="rounded-xl border border-border/70 bg-background/40 p-3">
      <p className={`text-xs font-semibold uppercase tracking-wide ${color}`}>{title}</p>
      <ul className="mt-2 space-y-1.5 text-sm text-foreground/90">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className={color}>{tone === "good" ? "✓" : "–"}</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExitCard({ tile }: { tile: Record<string, unknown> }) {
  const symbol = String(tile.symbol ?? "");
  return (
    <article className="rounded-xl border border-border bg-surface/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link
            href={`/stocks?ticker=${encodeURIComponent(symbol)}`}
            className="text-lg font-semibold text-accent hover:underline"
          >
            {symbol}
          </Link>
          <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-100">
            {String(tile.action || tile.label || "Review")}
          </span>
        </div>
        <span className="text-xs text-muted">
          Urgency {String(tile.exit_urgency ?? "—")}
          {tile.confidence != null ? ` · Conf ${String(tile.confidence)}` : ""}
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-foreground/90">
        {String(tile.takeaway || tile.primary_reason || "Review position against plan.")}
      </p>
      {tile.primary_reason && tile.takeaway ? (
        <p className="mt-2 text-xs text-muted">{String(tile.primary_reason)}</p>
      ) : null}
      {tile.main_risk ? (
        <p className="mt-2 rounded-lg bg-background/50 px-3 py-2 text-xs text-muted">
          <span className="font-semibold text-foreground/80">Main risk:</span> {String(tile.main_risk)}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          href="/options-intelligence"
          className="rounded-md bg-accent/20 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/30"
        >
          Review options flow
        </Link>
        <Link
          href={`/stocks?ticker=${encodeURIComponent(symbol)}`}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted hover:text-foreground"
        >
          Open chart
        </Link>
      </div>
    </article>
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
