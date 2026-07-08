"use client";

import Link from "next/link";
import { useState } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface PerformanceEntry {
  id: string;
  module: string;
  signal_id: string;
  outcome: string;
  return_pct?: number | null;
  hold_duration_hours?: number | null;
  logged_at?: string;
  resolution_source?: string | null;
  signal_label?: string | null;
}

export interface PerformanceSummary {
  days: number;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  avg_loss_pct?: number | null;
  total_signals?: number;
  wins?: number;
  losses?: number;
  scratches?: number;
  pending?: number;
  auto_resolved?: number;
  learning_active?: boolean;
  learning_notes?: string[];
  confidence_accuracy?: Record<string, { count: number; win_rate: number }>;
  calibration?: {
    sample_count?: number;
    learning_notes?: string[];
    active?: boolean;
  };
  by_module?: Record<string, PerformanceSummary>;
}

interface PerformanceViewProps {
  initialSummary: PerformanceSummary;
  initialHistory: PerformanceEntry[];
}

export function PerformanceView({ initialSummary, initialHistory }: PerformanceViewProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [history, setHistory] = useState(initialHistory);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [coachInsight, setCoachInsight] = useState<{
    narrative?: string;
    focus_areas?: string[];
    source?: string;
  } | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  async function refreshSummary() {
    const token = await getToken();
    const sumRes = await fetch(`${getApiUrl()}/performance/summary?days=30`, {
      headers: apiRequestHeaders(token),
    });
    if (sumRes.ok) {
      setSummary(await sumRes.json());
    }
    const histRes = await fetch(`${getApiUrl()}/performance/history?limit=30`, {
      headers: apiRequestHeaders(token),
    });
    if (histRes.ok) {
      const data = await histRes.json();
      setHistory(data.items ?? []);
    }
  }

  async function runResolve() {
    setLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/engine/resolve-outcomes`, {
        method: "POST",
        headers: apiRequestHeaders(token),
      });
      const body = await res.json();
      if (res.ok) {
        setMessage(
          body.resolved > 0
            ? `Auto-graded ${body.resolved} finished sports pick(s)`
            : "No new sports results to grade yet",
        );
        await refreshSummary();
      } else {
        setMessage("Could not auto-grade picks");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setLoading(false);
  }

  async function runAggregate() {
    setLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/engine/coach-aggregate`, {
        method: "POST",
        headers: apiRequestHeaders(token),
      });
      const body = await res.json();
      if (res.ok && body.summary) {
        setSummary(body.summary);
        setMessage("Performance summary updated");
      } else {
        setMessage("Aggregate failed");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setLoading(false);
  }

  async function loadCoachInsight() {
    setCoachLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/ai/coach-insight?refresh=true`, {
        headers: apiRequestHeaders(token),
      });
      if (res.ok) {
        setCoachInsight(await res.json());
        setMessage("AI coach insight updated");
      } else {
        setMessage("Could not load coach insight");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setCoachLoading(false);
  }

  const learningNotes = summary.learning_notes ?? summary.calibration?.learning_notes ?? [];
  const confidenceBuckets = summary.confidence_accuracy ?? {};

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
        <h2 className="text-sm font-semibold text-foreground">How Atlas learns</h2>
        <p className="mt-2 text-sm text-muted">
          Tap <strong className="text-foreground">Win</strong> or <strong className="text-foreground">Loss</strong> on
          any pick card after it settles. Sports picks auto-grade when final scores are available. After enough
          results, Atlas tightens thresholds so weaker edges surface less often.
        </p>
        {summary.learning_active && learningNotes.length > 0 ? (
          <ul className="mt-3 space-y-1 text-sm text-violet-200">
            {learningNotes.map((note) => (
              <li key={note}>· {note}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-xs text-muted">
            Log at least 8 outcomes across stocks, options, and sports to activate personalized learning.
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={runResolve}
            disabled={loading}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Grade finished sports picks
          </button>
          <button
            type="button"
            onClick={loadCoachInsight}
            disabled={loading || coachLoading}
            className="rounded-lg border border-sky-500/40 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/10 disabled:opacity-50"
          >
            {coachLoading ? "Thinking…" : "AI coach insight"}
          </button>
          <button
            type="button"
            onClick={runAggregate}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-surface-hover disabled:opacity-50"
          >
            Refresh summary
          </button>
        </div>
        {coachInsight?.narrative && (
          <div className="mt-4 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">
              {coachInsight.source === "openai" ? "AI coach" : "Coach summary"}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-foreground/90">{coachInsight.narrative}</p>
            {coachInsight.focus_areas && coachInsight.focus_areas.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm text-muted">
                {coachInsight.focus_areas.map((area) => (
                  <li key={area}>· {area}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {message && <p className="mt-3 text-sm text-muted">{message}</p>}
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Win rate (30d)" value={summary.win_rate != null ? `${summary.win_rate}%` : "—"} />
        <StatCard label="Avg win return" value={fmtPct(summary.avg_return_pct)} />
        <StatCard label="Logged trades" value={String(summary.total_signals ?? 0)} />
        <StatCard
          label="W / L / Auto"
          value={`${summary.wins ?? 0} / ${summary.losses ?? 0} / ${summary.auto_resolved ?? 0}`}
        />
      </section>

      {Object.keys(confidenceBuckets).length > 0 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Confidence vs actual results</h2>
          <p className="mt-1 text-xs text-muted">
            When Atlas is overconfident in a bucket, future scans adjust scores automatically.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(confidenceBuckets).map(([label, bucket]) => (
              <div key={label} className="rounded-lg border border-border bg-background/50 p-3">
                <p className="text-xs text-muted">Confidence {label}</p>
                <p className="mt-1 text-lg font-semibold">{bucket.win_rate}% win</p>
                <p className="text-xs text-muted">{bucket.count} picks</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold">Recent outcomes</h2>
        {history.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-surface text-xs text-muted">
                <tr>
                  <th className="px-4 py-2">Pick</th>
                  <th className="px-4 py-2">Module</th>
                  <th className="px-4 py-2">Outcome</th>
                  <th className="px-4 py-2">Return</th>
                  <th className="px-4 py-2">Logged</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.id} className="border-b border-border/50">
                    <td className="px-4 py-2 text-muted">
                      {row.signal_label ?? row.signal_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2 capitalize">{row.module}</td>
                    <td className="px-4 py-2 capitalize">
                      {row.outcome}
                      {row.resolution_source === "auto_sports" && (
                        <span className="ml-1 text-xs text-muted">(auto)</span>
                      )}
                    </td>
                    <td className="px-4 py-2">{fmtPct(row.return_pct)}</td>
                    <td className="px-4 py-2 text-muted">
                      {row.logged_at ? new Date(row.logged_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
            <p>No outcomes logged yet.</p>
            <p className="mt-2 text-sm">
              Open any{" "}
              <Link href="/sports" className="text-accent hover:underline">
                sports
              </Link>
              ,{" "}
              <Link href="/stocks" className="text-accent hover:underline">
                stock
              </Link>
              , or{" "}
              <Link href="/options" className="text-accent hover:underline">
                options
              </Link>{" "}
              pick and tap Win / Loss when it settles.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v}%`;
}
