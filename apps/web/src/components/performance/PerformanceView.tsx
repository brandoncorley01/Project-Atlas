"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildClientCoachInsight, type CoachInsight } from "@/lib/performance-coach";
import {
  backfillPerformanceTracking,
  fetchPerformanceHistory,
  fetchPerformanceSummary,
  updatePerformanceOutcome,
} from "@/lib/performance-api";
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

const SECTORS = [
  { id: "sports", label: "Sports", canAutoGrade: true },
  { id: "stock", label: "Stocks", canAutoGrade: true },
  { id: "options", label: "Options", canAutoGrade: true },
  { id: "parlay", label: "Parlays", canAutoGrade: false },
] as const;

type SectorId = (typeof SECTORS)[number]["id"];

export function PerformanceView({ initialSummary, initialHistory }: PerformanceViewProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [history, setHistory] = useState(initialHistory);
  const [loading, setLoading] = useState(false);
  const [gradingSector, setGradingSector] = useState<SectorId | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [coachInsight, setCoachInsight] = useState<CoachInsight | null>(null);
  const [coachLoading, setCoachLoading] = useState(true);
  const [coachError, setCoachError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"api" | "direct" | null>(null);
  const didAutoBackfill = useRef(false);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  const refreshSummary = useCallback(async () => {
    const token = await getToken();
    const creds = usesBffProxy() ? "include" : ("same-origin" as RequestCredentials);

    let usedApi = false;
    try {
      const sumRes = await fetch(`${getApiUrl()}/performance/summary?days=30`, {
        headers: apiRequestHeaders(token),
        cache: "no-store",
        credentials: creds,
      });
      const histRes = await fetch(`${getApiUrl()}/performance/history?limit=200`, {
        headers: apiRequestHeaders(token),
        cache: "no-store",
        credentials: creds,
      });
      if (sumRes.ok && histRes.ok) {
        setSummary(await sumRes.json());
        const data = await histRes.json();
        setHistory(data.items ?? []);
        setDataSource("api");
        usedApi = true;
      }
    } catch {
      /* fall through */
    }

    if (!usedApi) {
      const [sum, hist] = await Promise.all([
        fetchPerformanceSummary(30),
        fetchPerformanceHistory(200),
      ]);
      setSummary(sum);
      setHistory(hist);
      setDataSource("direct");
    }
  }, []);

  const loadCoachInsight = useCallback(
    async (refresh = false, summarySnapshot?: PerformanceSummary) => {
      const snapshot = summarySnapshot ?? summary;
      setCoachInsight(buildClientCoachInsight(snapshot));
      setCoachError(null);
      if (refresh) setCoachLoading(true);

      const token = await getToken();
      try {
        const params = new URLSearchParams({ days: "30" });
        if (refresh) params.set("refresh", "true");
        const res = await fetch(`${getApiUrl()}/ai/coach-insight?${params}`, {
          headers: apiRequestHeaders(token),
          credentials: usesBffProxy() ? "include" : "same-origin",
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok && body.narrative) {
          setCoachInsight(body);
        } else if (!res.ok) {
          const detail = typeof body.detail === "string" ? body.detail : null;
          if (detail && !detail.toLowerCase().includes("not found")) {
            setCoachError(`Using offline coach — ${detail}`);
          }
        }
      } catch {
        setCoachError("Using offline coach — API temporarily unavailable.");
      }
      setCoachLoading(false);
    },
    [summary],
  );

  const runBackfill = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      if (!silent) setMessage(null);
      try {
        const result = await backfillPerformanceTracking();
        if (result.source === "direct") {
          setDataSource("direct");
        }
        const registered = result.registered;
        const parts = Object.entries(result.by_module)
          .filter(([, v]) => (v?.registered ?? 0) > 0)
          .map(([k, v]) => `${k}: ${v?.registered}`);
        if (!silent || registered > 0) {
          const via = result.source === "direct" ? " (saved directly)" : "";
          setMessage(
            registered > 0
              ? `Registered ${registered} pick(s) for tracking${via}${parts.length ? ` — ${parts.join(", ")}` : ""}`
              : "All past picks are already tracked — try Grade on a sector below",
          );
        }
        await refreshSummary();
        void loadCoachInsight(true);
      } catch (err) {
        if (!silent) {
          setMessage(err instanceof Error ? err.message : "Could not register past picks");
        }
      }
      if (!silent) setLoading(false);
    },
    [loadCoachInsight, refreshSummary],
  );

  useEffect(() => {
    void refreshSummary().then(() => {
      void loadCoachInsight(false);
    });
    function onUpdated() {
      void refreshSummary();
    }
    window.addEventListener("atlas:performance-updated", onUpdated);
    return () => window.removeEventListener("atlas:performance-updated", onUpdated);
  }, [refreshSummary, loadCoachInsight]);

  useEffect(() => {
    setCoachInsight(buildClientCoachInsight(summary));
  }, [summary]);

  useEffect(() => {
    if (didAutoBackfill.current) return;
    const tracked = (summary.total_signals ?? 0) + (summary.pending ?? 0);
    if (tracked > 0 || history.length > 0) return;
    didAutoBackfill.current = true;
    void runBackfill(true);
  }, [summary, history.length, runBackfill]);

  const historyBySector = useMemo(() => {
    const grouped: Record<SectorId, { graded: PerformanceEntry[]; pending: PerformanceEntry[] }> = {
      sports: { graded: [], pending: [] },
      stock: { graded: [], pending: [] },
      options: { graded: [], pending: [] },
      parlay: { graded: [], pending: [] },
    };
    for (const row of history) {
      const mod = row.module as SectorId;
      if (!grouped[mod]) continue;
      if (row.outcome === "pending") {
        grouped[mod].pending.push(row);
      } else if (["win", "loss", "scratch"].includes(row.outcome)) {
        grouped[mod].graded.push(row);
      }
    }
    return grouped;
  }, [history]);

  async function runResolveSector(sectorId: SectorId) {
    setGradingSector(sectorId);
    setMessage(null);
    const token = await getToken();
    const sector = SECTORS.find((s) => s.id === sectorId);
    try {
      const params = new URLSearchParams({ module: sectorId });
      const res = await fetch(`${getApiUrl()}/engine/resolve-outcomes?${params}`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        const resolved = body.resolved ?? 0;
        const skipped = body.skipped ?? 0;
        const modResult = body.by_module?.[sectorId] as { resolved?: number; pending?: number } | undefined;
        let msg =
          resolved > 0
            ? `Auto-graded ${resolved} ${sector?.label.toLowerCase() ?? sectorId} pick(s)`
            : skipped > 0
              ? `No new grades — ${skipped} ${sector?.label.toLowerCase() ?? sectorId} pick(s) still awaiting final data`
              : `No ${sector?.label.toLowerCase() ?? sectorId} picks ready to grade yet`;
        if (modResult && resolved === 0 && (modResult.pending ?? 0) > 0) {
          msg += ` (${modResult.pending} pending in this sector)`;
        }
        setMessage(msg);
        await refreshSummary();
        void loadCoachInsight(true);
      } else {
        const detail = typeof body.detail === "string" ? body.detail : "Could not auto-grade picks";
        setMessage(detail);
      }
    } catch {
      setMessage("Backend not responding");
    }
    setGradingSector(null);
  }

  async function runAggregate() {
    setLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/engine/coach-aggregate`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      const body = await res.json();
      if (res.ok && body.summary) {
        setSummary(body.summary);
        setMessage("Performance summary updated");
        void loadCoachInsight(true);
      } else {
        setMessage("Aggregate failed");
      }
    } catch {
      setMessage("Backend not responding");
    }
    setLoading(false);
  }

  const learningNotes = summary.learning_notes ?? summary.calibration?.learning_notes ?? [];
  const confidenceBuckets = summary.confidence_accuracy ?? {};

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
        <h2 className="text-sm font-semibold text-foreground">How Atlas learns</h2>
        <p className="mt-2 text-sm text-muted">
          Tap <strong className="text-foreground">Win</strong> or <strong className="text-foreground">Loss</strong> on
          any pick card after it settles. <strong className="text-foreground">Every scan is auto-tracked</strong> — Atlas
          also grades sports, stocks, and options when they expire. After enough results, thresholds tighten automatically.
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
            onClick={() => void loadCoachInsight(true)}
            disabled={loading || coachLoading}
            className="rounded-lg border border-sky-500/40 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/10 disabled:opacity-50"
          >
            {coachLoading ? "Loading coach…" : "Refresh coach insight"}
          </button>
          <button
            type="button"
            onClick={() => void runBackfill(false)}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-surface-hover disabled:opacity-50"
          >
            Register all past picks
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

        <div className="mt-4 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">
            {coachInsight?.source === "openai" ? "AI coach" : "Coach summary"}
          </p>
          {coachLoading ? (
            <p className="mt-2 text-sm text-muted">Loading your performance insight…</p>
          ) : coachInsight?.narrative ? (
            <>
              {coachError && <p className="mt-2 text-xs text-amber-300/90">{coachError}</p>}
              <p className="mt-2 text-sm leading-relaxed text-foreground/90">{coachInsight.narrative}</p>
              {coachInsight.focus_areas && coachInsight.focus_areas.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm text-muted">
                  {coachInsight.focus_areas.map((area) => (
                    <li key={area}>· {area}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="mt-2 text-sm text-muted">
              Grade a few settled picks to unlock personalized coaching.
            </p>
          )}
        </div>

        {message && <p className="mt-3 text-sm text-muted">{message}</p>}
        {dataSource === "direct" && (
          <p className="mt-2 text-xs text-amber-300/80">
            Tracking via Supabase directly — API backend unreachable. Grading and saves still work.
          </p>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Win rate (30d)" value={summary.win_rate != null ? `${summary.win_rate}%` : "—"} />
        <StatCard label="Avg win return" value={fmtPct(summary.avg_return_pct)} />
        <StatCard label="Logged trades" value={String(summary.total_signals ?? 0)} />
        <StatCard
          label="W / L / Auto"
          value={`${summary.wins ?? 0} / ${summary.losses ?? 0} / ${summary.auto_resolved ?? 0}`}
        />
        <StatCard label="Awaiting grade" value={String(summary.pending ?? 0)} />
      </section>

      {SECTORS.map((sector) => {
        const modSummary = summary.by_module?.[sector.id];
        const sectorHistory = historyBySector[sector.id];
        const sectorCoach = coachInsight?.by_module?.[sector.id];
        const isGrading = gradingSector === sector.id;

        return (
          <SectorSection
            key={sector.id}
            sector={sector}
            summary={modSummary}
            graded={sectorHistory.graded}
            pending={sectorHistory.pending}
            coachNarrative={sectorCoach?.narrative}
            isGrading={isGrading}
            onGrade={() => void runResolveSector(sector.id)}
            onUpdated={refreshSummary}
          />
        );
      })}

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
    </div>
  );
}

function SectorSection({
  sector,
  summary,
  graded,
  pending,
  coachNarrative,
  isGrading,
  onGrade,
  onUpdated,
}: {
  sector: (typeof SECTORS)[number];
  summary?: PerformanceSummary;
  graded: PerformanceEntry[];
  pending: PerformanceEntry[];
  coachNarrative?: string;
  isGrading: boolean;
  onGrade: () => void;
  onUpdated: () => Promise<void>;
}) {
  const winRate = summary?.win_rate;
  const totalGraded = summary?.total_signals ?? graded.length;
  const awaiting = summary?.pending ?? pending.length;

  return (
    <section className="rounded-xl border border-border bg-surface/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{sector.label}</h2>
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted">
            <span>
              Win rate:{" "}
              <strong className="text-foreground">{winRate != null ? `${winRate}%` : "—"}</strong>
            </span>
            <span>
              Graded: <strong className="text-foreground">{totalGraded}</strong>
            </span>
            <span>
              Awaiting: <strong className="text-foreground">{awaiting}</strong>
            </span>
            {summary && (summary.wins != null || summary.losses != null) && (
              <span>
                W/L:{" "}
                <strong className="text-foreground">
                  {summary.wins ?? 0} / {summary.losses ?? 0}
                </strong>
              </span>
            )}
          </div>
        </div>
        {sector.canAutoGrade ? (
          <button
            type="button"
            onClick={onGrade}
            disabled={isGrading}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {isGrading ? "Grading…" : `Grade ${sector.label.toLowerCase()}`}
          </button>
        ) : (
          <Link
            href="/watchlist"
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-surface-hover"
          >
            Grade on watchlist
          </Link>
        )}
      </div>

      {coachNarrative && (
        <p className="mt-3 text-sm text-sky-200/90">{coachNarrative}</p>
      )}

      {graded.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-surface text-xs text-muted">
              <tr>
                <th className="px-4 py-2">Pick</th>
                <th className="px-4 py-2">Outcome</th>
                <th className="px-4 py-2">Return</th>
                <th className="px-4 py-2">Logged / Edit</th>
              </tr>
            </thead>
            <tbody>
              {graded.map((row) => (
                <OutcomeRow key={row.id} row={row} onUpdated={onUpdated} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-dashed border-border bg-background/30 p-6 text-center text-sm text-muted">
          <p>No graded {sector.label.toLowerCase()} picks yet.</p>
          {sector.canAutoGrade ? (
            <p className="mt-2">
              Tap <strong className="text-foreground">Grade {sector.label.toLowerCase()}</strong> when games or
              positions settle, or log Win/Loss on your{" "}
              <Link href="/watchlist" className="text-accent hover:underline">
                watchlist
              </Link>
              .
            </p>
          ) : (
            <p className="mt-2">
              Save parlays to your{" "}
              <Link href="/watchlist" className="text-accent hover:underline">
                watchlist
              </Link>{" "}
              and tap Win/Loss when they settle.
            </p>
          )}
        </div>
      )}

      {pending.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
            Awaiting grade ({pending.length})
          </h3>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {pending.slice(0, 5).map((row) => (
              <li key={row.id} className="flex justify-between gap-2 border-b border-border/40 py-1">
                <span>{row.signal_label ?? row.signal_id.slice(0, 8)}</span>
                <span className="shrink-0 text-xs">pending</span>
              </li>
            ))}
            {pending.length > 5 && (
              <li className="text-xs text-muted">+ {pending.length - 5} more on watchlist</li>
            )}
          </ul>
        </div>
      )}
    </section>
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

function OutcomeRow({
  row,
  onUpdated,
}: {
  row: PerformanceEntry;
  onUpdated: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [outcome, setOutcome] = useState(row.outcome);
  const [returnPct, setReturnPct] = useState(
    row.return_pct != null ? String(row.return_pct) : "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOutcome(row.outcome);
    setReturnPct(row.return_pct != null ? String(row.return_pct) : "");
  }, [row.id, row.outcome, row.return_pct]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const returnVal = returnPct.trim() !== "" ? Number(returnPct) : undefined;
      const saved = await updatePerformanceOutcome(row.id, {
        outcome,
        returnPct: returnVal,
      });
      if (!saved) {
        throw new Error("Update failed");
      }
      setEditing(false);
      await onUpdated();
      window.dispatchEvent(new CustomEvent("atlas:performance-updated"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update outcome");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="border-b border-border/50">
      <td className="px-4 py-2 text-muted">
        {row.signal_label ?? row.signal_id.slice(0, 8)}
      </td>
      <td className="px-4 py-2">
        {editing ? (
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-sm capitalize"
          >
            <option value="win">Win</option>
            <option value="loss">Loss</option>
            <option value="scratch">Scratch</option>
            <option value="pending">Pending</option>
          </select>
        ) : (
          <span className="capitalize">
            {row.outcome}
            {row.resolution_source === "auto_sports" && (
              <span className="ml-1 text-xs text-muted">(auto)</span>
            )}
            {String(row.resolution_source ?? "").startsWith("auto_") &&
              row.resolution_source !== "auto_sports" && (
                <span className="ml-1 text-xs text-muted">(auto)</span>
              )}
            {(row.resolution_source === "manual" || row.resolution_source === "manual_edit") && (
              <span className="ml-1 text-xs text-muted">(you)</span>
            )}
          </span>
        )}
      </td>
      <td className="px-4 py-2">
        {editing ? (
          <input
            type="number"
            step="0.1"
            placeholder="Return %"
            value={returnPct}
            onChange={(e) => setReturnPct(e.target.value)}
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm"
          />
        ) : (
          fmtPct(row.return_pct)
        )}
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-col gap-1">
          <span className="text-muted">
            {row.logged_at ? new Date(row.logged_at).toLocaleDateString() : "—"}
          </span>
          {editing ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setOutcome(row.outcome);
                  setReturnPct(row.return_pct != null ? String(row.return_pct) : "");
                  setError(null);
                }}
                className="text-xs text-muted hover:underline"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-left text-xs font-medium text-accent hover:underline"
            >
              Edit
            </button>
          )}
          {error && <span className="text-xs text-danger">{error}</span>}
        </div>
      </td>
    </tr>
  );
}
