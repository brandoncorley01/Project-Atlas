"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { usesBffProxy } from "@/lib/api-url";

interface AtlasExplainButtonProps {
  module: "options" | "stock" | "sports";
  signalId: string;
  className?: string;
}

interface NewsArticle {
  title?: string;
  url?: string;
  source?: string;
  summary?: string | null;
}

interface TeamSide {
  label?: string;
  name?: string;
  record?: string;
  win_pct?: number;
  avg_scored?: number;
  avg_allowed?: number;
}

interface StatsComparison {
  summary?: string;
  home?: TeamSide;
  away?: TeamSide;
  h2h?: { home_wins?: number; away_wins?: number; draws?: number; games?: number };
  pick_support?: number;
  selection?: string;
}

interface ExplainResponse {
  explanation?: string;
  bullets?: string[];
  risks?: string[];
  news_articles?: NewsArticle[];
  stats_comparison?: StatsComparison;
  source?: string;
}

export function AtlasExplainButton({ module, signalId, className }: AtlasExplainButtonProps) {
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
        timeoutMs: module === "sports" ? 45_000 : 25_000,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load explanation");
    } finally {
      setLoading(false);
    }
  }

  const stats = data?.stats_comparison;
  const news = data?.news_articles ?? [];

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => void loadExplanation()}
        disabled={loading}
        className="text-xs font-medium text-sky-300 hover:text-sky-200 hover:underline disabled:opacity-50"
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
                ? "Searching headlines, pulling team stats, and building insight…"
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
              {data.source === "openai" && (
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-sky-200/70">
                  AI insight
                </p>
              )}

              {module === "sports" && stats && (
                <div className="mb-3 rounded-md border border-border/60 bg-background/40 p-2.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Stats comparison
                  </p>
                  {stats.summary && (
                    <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">{stats.summary}</p>
                  )}
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {[stats.home, stats.away].map(
                      (side) =>
                        side?.name && (
                          <div key={side.name} className="rounded border border-border/50 px-2 py-1.5 text-xs">
                            <p className="font-medium">{side.name}</p>
                            {side.record && <p className="text-muted">Record: {side.record}</p>}
                            {side.win_pct != null && <p className="text-muted">Win %: {side.win_pct}%</p>}
                            {side.avg_scored != null && side.avg_allowed != null && (
                              <p className="text-muted">
                                Avg {side.avg_scored} scored · {side.avg_allowed} allowed
                              </p>
                            )}
                          </div>
                        ),
                    )}
                  </div>
                  {stats.h2h?.games ? (
                    <p className="mt-2 text-xs text-muted">
                      H2H: {stats.h2h.home_wins}-{stats.h2h.away_wins}
                      {stats.h2h.draws ? `-${stats.h2h.draws}` : ""} ({stats.h2h.games} games)
                    </p>
                  ) : null}
                </div>
              )}

              {module === "sports" && news.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">Related news</p>
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
                        {article.source && (
                          <span className="ml-1 text-xs text-muted">· {article.source}</span>
                        )}
                        {article.summary && (
                          <p className="mt-0.5 text-xs text-muted line-clamp-2">{article.summary}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {module === "sports" && news.length === 0 && (
                <p className="mb-3 text-xs text-muted">
                  No closely matched headlines right now — check lineups before kickoff.
                </p>
              )}

              {data.explanation && (
                <p className="text-sm leading-relaxed text-foreground/90">{data.explanation}</p>
              )}
              {data.bullets && data.bullets.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-muted">
                  {data.bullets.map((b) => (
                    <li key={b}>· {b}</li>
                  ))}
                </ul>
              )}
              {data.risks && data.risks.length > 0 && (
                <div className="mt-3 border-t border-border/50 pt-2">
                  <p className="text-xs font-semibold text-amber-200/80">Risks</p>
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
