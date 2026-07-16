"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { usesBffProxy } from "@/lib/api-url";

interface AtlasExplainButtonProps {
  module: "options" | "stock" | "sports";
  signalId: string;
  className?: string;
  /** Card thesis used when the explain API times out or returns empty. */
  fallbackThesis?: string | null;
}

interface NewsArticle {
  title?: string;
  url?: string;
  source?: string;
  summary?: string | null;
  context_tier?: string;
}

interface TeamSide {
  label?: string;
  name?: string;
  record?: string;
  win_pct?: number;
  avg_scored?: number;
  avg_allowed?: number;
  form?: string;
  home_record?: string;
  away_record?: string;
  games_sampled?: number;
}

interface KeyMetricRow {
  key?: string;
  label?: string;
  home?: string | number | null;
  away?: string | number | null;
  edge?: "home" | "away" | "even" | null;
  delta?: number | null;
  note?: string;
}

interface StatsComparison {
  summary?: string;
  analysis?: string;
  title?: string;
  sport_family?: string;
  home?: TeamSide;
  away?: TeamSide;
  h2h?: { home_wins?: number; away_wins?: number; draws?: number; games?: number };
  pick_support?: number;
  selection?: string;
  available?: boolean;
  key_metrics?: KeyMetricRow[];
  metric_labels?: Record<string, string>;
}

interface MarketContext {
  selection?: string;
  bet_type?: string;
  odds_american?: number;
  expected_value?: number;
  edge_pct?: number;
  opportunity?: number;
  confidence?: number;
  risk?: number;
  sharp_indicator?: string | null;
}

interface ExplainResponse {
  explanation?: string;
  why_atlas?: string;
  pick_thesis?: string;
  bullets?: string[];
  risks?: string[];
  news_articles?: NewsArticle[];
  stats_comparison?: StatsComparison;
  market?: MarketContext;
  source?: string;
}

export function AtlasExplainButton({
  module,
  signalId,
  className,
  fallbackThesis,
}: AtlasExplainButtonProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadExplanation(force = false) {
    if (data && open && !force) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (data && !force) return;

    setLoading(true);
    setError(null);
    setData(null);
    try {
      let token: string | undefined;
      if (!usesBffProxy()) {
        const { data: session } = await createClient().auth.getSession();
        token = session.session?.access_token;
      }
      const result = await apiFetch<ExplainResponse>("/ai/explain", token, {
        method: "POST",
        body: JSON.stringify({ module, signal_id: signalId }),
        // Sports pulls news + form + optional LLM — give the BFF room under its 90s AI budget.
        timeoutMs: module === "sports" ? 80_000 : 25_000,
      });
      const thesis =
        result.why_atlas || result.pick_thesis || result.explanation || fallbackThesis || "";
      if (!thesis && !result.bullets?.length) {
        setData({
          ...result,
          why_atlas:
            fallbackThesis ||
            "Atlas could not build a deeper write-up for this pick yet. Market scores on the card above are still valid — try again in a moment.",
          explanation: fallbackThesis || result.explanation,
          source: result.source || "template",
        });
      } else {
        setData({
          ...result,
          why_atlas: thesis,
          pick_thesis: result.pick_thesis || thesis,
          explanation: result.explanation || thesis,
        });
      }
    } catch (err) {
      if (fallbackThesis) {
        setData({
          why_atlas: fallbackThesis,
          pick_thesis: fallbackThesis,
          explanation: fallbackThesis,
          source: "template",
        });
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Could not load explanation");
      }
    } finally {
      setLoading(false);
    }
  }

  const stats = data?.stats_comparison;
  const news = data?.news_articles ?? [];
  const market = data?.market;
  const whyAtlas =
    data?.why_atlas || data?.pick_thesis || data?.explanation || "";

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => void loadExplanation()}
        disabled={loading}
        className="inline-flex items-center rounded-lg border border-sky-400/40 bg-sky-500/15 px-3.5 py-2 text-sm font-semibold text-sky-100 hover:bg-sky-500/25 disabled:opacity-50"
      >
        {loading
          ? "Atlas is researching…"
          : open && data
            ? "Hide Atlas insight"
            : "Ask Atlas for deeper insight"}
      </button>

      {open && (
        <div className="mt-3 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
          {loading && (
            <p className="text-sm text-muted">
              {module === "sports"
                ? "Pulling market data, team form, headlines, and building why Atlas chose this pick…"
                : "Building explanation from scan data…"}
            </p>
          )}
          {error && (
            <div className="space-y-2">
              <p className="text-sm text-danger">{error}</p>
              <button
                type="button"
                onClick={() => void loadExplanation(true)}
                className="text-xs font-medium text-sky-300 hover:underline"
              >
                Try again
              </button>
            </div>
          )}
          {data && !loading && (
            <>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-sky-200/70">
                {data.source === "openai" ? "Why Atlas chose this pick" : "Atlas pick thesis"}
              </p>

              {module === "sports" && market && (
                <div className="mb-3 flex flex-wrap gap-1.5 text-[11px]">
                  {market.odds_american != null && (
                    <span className="rounded bg-background/60 px-1.5 py-0.5 text-muted">
                      Odds {market.odds_american > 0 ? "+" : ""}
                      {market.odds_american}
                    </span>
                  )}
                  {market.expected_value != null && (
                    <span className="rounded bg-background/60 px-1.5 py-0.5 text-muted">
                      EV {market.expected_value >= 0 ? "+" : ""}
                      {Number(market.expected_value).toFixed(1)}%
                    </span>
                  )}
                  {market.edge_pct != null && (
                    <span className="rounded bg-background/60 px-1.5 py-0.5 text-muted">
                      Edge {Number(market.edge_pct) >= 0 ? "+" : ""}
                      {Number(market.edge_pct).toFixed(1)}%
                    </span>
                  )}
                  {market.opportunity != null && (
                    <span className="rounded bg-background/60 px-1.5 py-0.5 text-muted">
                      Opp {Number(market.opportunity).toFixed(0)}
                    </span>
                  )}
                  {market.confidence != null && (
                    <span className="rounded bg-background/60 px-1.5 py-0.5 text-muted">
                      Conf {Number(market.confidence).toFixed(0)}
                    </span>
                  )}
                </div>
              )}

              {whyAtlas && (
                <p className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
                  {whyAtlas}
                </p>
              )}

              {data.bullets && data.bullets.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Key factors
                  </p>
                  <ul className="mt-1.5 space-y-1 text-sm text-muted">
                    {data.bullets.map((b) => (
                      <li key={b}>· {b}</li>
                    ))}
                  </ul>
                </div>
              )}

              {module === "sports" && stats && (
                <div className="mt-3 rounded-md border border-border/60 bg-background/40 p-2.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    {stats.title || "Stats & form"} · key matchup metrics
                  </p>
                  {(stats.analysis || stats.summary) && (
                    <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">
                      {stats.analysis || stats.summary}
                    </p>
                  )}

                  {stats.key_metrics && stats.key_metrics.length > 0 ? (
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full min-w-[280px] text-left text-xs">
                        <thead>
                          <tr className="border-b border-border/50 text-muted">
                            <th className="py-1.5 pr-2 font-medium">Key</th>
                            <th className="py-1.5 pr-2 font-medium">
                              {stats.home?.name || "Home"}
                            </th>
                            <th className="py-1.5 pr-2 font-medium">
                              {stats.away?.name || "Away"}
                            </th>
                            <th className="py-1.5 font-medium">Edge</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.key_metrics.map((row) => (
                            <tr key={row.key || row.label} className="border-b border-border/30">
                              <td className="py-1.5 pr-2 text-muted">{row.label}</td>
                              <td
                                className={`py-1.5 pr-2 ${
                                  row.edge === "home" ? "font-semibold text-emerald-200" : "text-foreground/90"
                                }`}
                              >
                                {row.home ?? "—"}
                              </td>
                              <td
                                className={`py-1.5 pr-2 ${
                                  row.edge === "away" ? "font-semibold text-emerald-200" : "text-foreground/90"
                                }`}
                              >
                                {row.away ?? "—"}
                              </td>
                              <td className="py-1.5 text-muted">
                                {row.edge === "home"
                                  ? stats.home?.name?.split(" ").slice(-1)[0] || "Home"
                                  : row.edge === "away"
                                    ? stats.away?.name?.split(" ").slice(-1)[0] || "Away"
                                    : row.edge === "even"
                                      ? "Even"
                                      : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {[stats.home, stats.away].map(
                        (side) =>
                          side?.name && (
                            <div
                              key={side.name}
                              className="rounded border border-border/50 px-2 py-1.5 text-xs"
                            >
                              <p className="font-medium">{side.name}</p>
                              {side.record && <p className="text-muted">Record: {side.record}</p>}
                              {side.form && <p className="text-muted">Form: {side.form}</p>}
                              {side.win_pct != null && (
                                <p className="text-muted">Win %: {side.win_pct}%</p>
                              )}
                              {side.avg_scored != null && side.avg_allowed != null && (
                                <p className="text-muted">
                                  Avg {side.avg_scored} scored · {side.avg_allowed} allowed
                                </p>
                              )}
                            </div>
                          ),
                      )}
                    </div>
                  )}

                  {stats.h2h?.games ? (
                    <p className="mt-2 text-xs text-muted">
                      H2H: {stats.h2h.home_wins}-{stats.h2h.away_wins}
                      {stats.h2h.draws ? `-${stats.h2h.draws}` : ""} ({stats.h2h.games} games)
                    </p>
                  ) : null}
                  {stats.available === false && (
                    <p className="mt-2 text-[11px] text-muted">
                      Recent completed-score sample is thin for this league window — Atlas still
                      frames the sport&apos;s key comparison metrics and leans on market edge until
                      more results land.
                    </p>
                  )}
                </div>
              )}

              {module === "sports" && news.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    News & context
                  </p>
                  <ul className="mt-1.5 space-y-2">
                    {news.map((article) => (
                      <li key={article.url ?? article.title} className="text-sm">
                        {article.url ? (
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-sky-200 hover:underline"
                          >
                            {article.title}
                          </a>
                        ) : (
                          <span className="font-medium">{article.title}</span>
                        )}
                        <span className="ml-1 text-xs text-muted">
                          {article.source ? `· ${article.source}` : ""}
                          {article.context_tier === "sport" ? " · sport context" : ""}
                        </span>
                        {article.summary && (
                          <p className="mt-0.5 text-xs text-muted line-clamp-2">{article.summary}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {data.risks && data.risks.length > 0 && (
                <div className="mt-3 border-t border-border/50 pt-2">
                  <p className="text-xs font-semibold text-amber-200/80">What could go wrong</p>
                  <ul className="mt-1 space-y-1 text-xs text-muted">
                    {data.risks.map((r) => (
                      <li key={r}>· {r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
