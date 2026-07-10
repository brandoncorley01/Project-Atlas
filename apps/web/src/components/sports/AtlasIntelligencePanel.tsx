"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  fetchSportsIntelligence,
  refreshSportsIntelligence,
  type AtlasIntelligencePayload,
} from "@/lib/sports-intelligence-api";

function confidenceClass(label: string) {
  if (label === "High Conviction" || label === "Strong") return "text-emerald-300 bg-emerald-500/15";
  if (label === "Avoid" || label === "Low Confidence") return "text-rose-300 bg-rose-500/15";
  return "text-amber-300 bg-amber-500/15";
}

function agreementLabel(status: string) {
  if (status === "agrees") return "Agrees with Atlas";
  if (status === "lean_agrees") return "Leans with Atlas";
  if (status === "disagrees") return "Disagrees with Atlas";
  if (status === "mixed") return "Mixed signals";
  return "Limited expert data";
}

function formatUpdated(iso?: string | null) {
  if (!iso) return "Unknown";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatPp(value: number) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}

export function AtlasIntelligencePanel({ signalId }: { signalId: string }) {
  const [data, setData] = useState<AtlasIntelligencePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) {
        setData(null);
        return;
      }
      const payload = await fetchSportsIntelligence(signalId, token);
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load intelligence");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [signalId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const supabase = createClient();
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) return;
      const payload = await refreshSportsIntelligence(signalId, token);
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <section className="mt-6 rounded-xl border border-border/60 bg-surface/50 p-5 text-sm text-muted">
        Loading Atlas Intelligence…
      </section>
    );
  }

  if (!data?.enabled) return null;

  if (data.status === "empty") {
    return (
      <section className="mt-6 rounded-xl border border-violet-500/30 bg-gradient-to-br from-violet-500/10 to-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-violet-200">Atlas Intelligence</h2>
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={refreshing}
            className="rounded-lg border border-violet-500/40 px-3 py-1.5 text-xs font-medium text-violet-200 hover:bg-violet-500/10 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh sources"}
          </button>
        </div>
        <p className="mt-2 text-sm text-muted">
          {data.message ?? "No intelligence cached yet for this event."}
        </p>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </section>
    );
  }

  const rec = data.atlas_recommendation;
  const consensus = data.expert_consensus;
  const transparency = data.source_transparency;

  return (
    <section className="mt-6 space-y-4 rounded-xl border border-violet-500/35 bg-gradient-to-br from-violet-500/10 via-surface to-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-violet-200">Atlas Intelligence</h2>
          <p className="mt-1 text-xs text-muted">
            Updated {formatUpdated(data.last_updated)} ·{" "}
            {transparency?.sources_analyzed ?? 0} sources ·{" "}
            {transparency?.unique_analysts ?? 0} analysts
          </p>
        </div>
        <button
          type="button"
          onClick={() => void onRefresh()}
          disabled={refreshing}
          className="rounded-lg border border-violet-500/40 px-3 py-1.5 text-xs font-medium text-violet-200 hover:bg-violet-500/10 disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {rec && (
        <div className="rounded-xl border border-border/60 bg-background/40 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-muted">Atlas Recommendation</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold">{rec.selection}</span>
            {rec.odds_american != null && (
              <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                {rec.odds_american > 0 ? "+" : ""}
                {rec.odds_american}
              </span>
            )}
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${confidenceClass(rec.confidence_label)}`}
            >
              {rec.confidence_label}
            </span>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <Metric label="Model confidence" value={`${rec.raw_confidence.toFixed(0)}%`} />
            <Metric
              label="Intel-adjusted"
              value={`${rec.adjusted_confidence.toFixed(0)}%`}
              highlight
            />
            {rec.expected_value != null && (
              <Metric
                label="Expected value"
                value={`${rec.expected_value >= 0 ? "+" : ""}${rec.expected_value.toFixed(1)}%`}
              />
            )}
          </div>
          {rec.primary_reasons && rec.primary_reasons.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
              {rec.primary_reasons.filter(Boolean).slice(0, 4).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {rec.invalidation && (
            <p className="mt-3 text-sm text-danger">
              <span className="font-medium">Invalidation:</span> {rec.invalidation}
            </p>
          )}
        </div>
      )}

      {consensus && (
        <div className="rounded-xl border border-border/60 bg-background/40 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-muted">Expert Consensus</p>
          <div className="mt-2 flex flex-wrap gap-2 text-sm">
            <Badge>{consensus.expert_count} experts</Badge>
            <Badge>Strength {consensus.weighted_consensus_score.toFixed(0)}/100</Badge>
            <Badge>{agreementLabel(consensus.model_agreement)}</Badge>
          </div>
          {consensus.majority_selection && (
            <p className="mt-2 text-sm">
              Majority: <span className="font-medium">{consensus.majority_selection}</span>
              {consensus.minority_selection && (
                <span className="text-muted"> · Minority: {consensus.minority_selection}</span>
              )}
            </p>
          )}
          <p className="mt-1 text-xs text-muted">
            {consensus.experts_agreeing_with_atlas} agreeing with Atlas ·{" "}
            {consensus.experts_disagreeing_with_atlas} disagreeing ·{" "}
            {consensus.source_count} source orgs
          </p>
        </div>
      )}

      {(data.supporting_analysts?.length ?? 0) > 0 ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">
            Analysts Backing Atlas
          </p>
          <p className="mt-1 text-xs text-muted">
            Only sources that support Atlas on {rec?.selection ?? "this pick"}
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {data.supporting_analysts!.slice(0, 6).map((card, idx) => (
              <article
                key={`${card.source}-support-${idx}`}
                className="rounded-lg border border-border/50 bg-surface/60 p-3 text-sm"
              >
                <p className="text-xs text-muted">
                  {card.source}
                  {card.analyst ? ` · ${card.analyst}` : ""}
                </p>
                {card.pick && <p className="mt-1 font-medium text-emerald-200">{card.pick}</p>}
                {(card.title || card.reasoning?.[0]) && (
                  <p className="mt-1 text-muted line-clamp-3">{card.title || card.reasoning?.[0]}</p>
                )}
                {card.url && (
                  <a
                    href={card.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs text-accent hover:underline"
                  >
                    View source
                  </a>
                )}
              </article>
            ))}
          </div>
        </div>
      ) : (data.analyst_cards?.length ?? 0) > 0 ? (
        <div className="rounded-xl border border-border/60 bg-background/40 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-muted">
            What Analysts Are Saying
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {data.analyst_cards!.slice(0, 6).map((card, idx) => (
              <article
                key={`${card.source}-${idx}`}
                className="rounded-lg border border-border/50 bg-surface/60 p-3 text-sm"
              >
                <p className="text-xs text-muted">
                  {card.source}
                  {card.analyst ? ` · ${card.analyst}` : ""}
                </p>
                {card.pick && <p className="mt-1 font-medium">{card.pick}</p>}
                {card.reasoning?.[0] && (
                  <p className="mt-1 text-muted line-clamp-3">{card.reasoning[0]}</p>
                )}
                {card.url && (
                  <a
                    href={card.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs text-accent hover:underline"
                  >
                    View source
                  </a>
                )}
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {(data.news_updates?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-sky-300">
            Key News & Updates
          </p>
          <ul className="mt-3 space-y-2">
            {data.news_updates!.slice(0, 5).map((item, idx) => (
              <li key={`${item.title}-${idx}`} className="text-sm">
                <span className="font-medium">{item.title}</span>
                {item.summary && (
                  <p className="mt-0.5 text-xs text-muted line-clamp-2">{item.summary}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {data.bull_case && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm">
            <p className="text-xs font-bold uppercase text-emerald-300">Bull Case</p>
            <p className="mt-2 text-muted">{data.bull_case}</p>
          </div>
        )}
        {data.bear_case && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm">
            <p className="text-xs font-bold uppercase text-rose-300">Bear Case</p>
            <p className="mt-2 text-muted">{data.bear_case}</p>
          </div>
        )}
      </div>

      {data.verdict && (
        <div className="rounded-xl border border-violet-500/25 bg-violet-500/5 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-violet-300">Atlas Verdict</p>
          <p className="mt-2 text-sm leading-relaxed">{data.verdict}</p>
        </div>
      )}

      <button
        type="button"
        onClick={() => setSourcesOpen((v) => !v)}
        className="text-xs font-medium text-accent hover:underline"
      >
        {sourcesOpen ? "Hide" : "Show"} source transparency
      </button>

      {sourcesOpen && transparency && (
        <div className="rounded-lg border border-border/50 bg-background/30 p-3 text-xs text-muted">
          <p>Items analyzed: {transparency.items_active}</p>
          <p>Video transcripts: {transparency.video_transcripts_available ? "Yes" : "No"}</p>
          <p>Major injury info flagged: {transparency.injury_confirmed ? "Yes" : "Unconfirmed"}</p>
          <p>Summaries generated by Atlas: {transparency.atlas_summarized ? "Yes" : "No"}</p>
          {data.adjustment && (
            <p className="mt-2">
              Adjustments (pp): expert {formatPp(data.adjustment.expert)}, news{" "}
              {formatPp(data.adjustment.news)}, injury {formatPp(data.adjustment.injury)}, penalty -
              {data.adjustment.disagreement_penalty.toFixed(1)}
            </p>
          )}
        </div>
      )}

      {data.disclaimer && <p className="text-xs text-muted">{data.disclaimer}</p>}
    </section>
  );
}

function Metric({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-lg px-3 py-2 ${highlight ? "bg-violet-500/10" : "bg-background/50"}`}>
      <p className="text-xs text-muted">{label}</p>
      <p className={`text-sm font-semibold ${highlight ? "text-violet-200" : ""}`}>{value}</p>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-background px-2 py-0.5 text-xs text-muted">{children}</span>
  );
}
