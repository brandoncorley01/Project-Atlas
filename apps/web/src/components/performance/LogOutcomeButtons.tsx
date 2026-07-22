"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getPerformanceOutcome,
  logPerformanceOutcome,
  syncAtlasLearningAfterOutcome,
} from "@/lib/performance-api";

type Outcome = "win" | "loss" | "scratch";

interface LogOutcomeButtonsProps {
  module: "options" | "stock" | "sports" | "parlay";
  signalId: string;
  signalSnapshot?: Record<string, unknown>;
  compact?: boolean;
  className?: string;
  /** Called after a successful grade/change so parents can refresh. */
  onLogged?: () => void | Promise<void>;
}

interface OutcomeEntry {
  outcome: string;
  resolution_source?: string | null;
  return_pct?: number | null;
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function normalizeSignalId(signalId: string): string {
  const trimmed = signalId.trim();
  return UUID_RE.test(trimmed) ? trimmed.toLowerCase() : trimmed;
}

function moduleHint(module: LogOutcomeButtonsProps["module"], compact: boolean) {
  if (compact) {
    return module === "options" || module === "stock" || module === "parlay"
      ? "Pick a result, then Save"
      : "Pick a result, then Save";
  }
  if (module === "options") {
    return "Closed this options position? Select Win / Loss / Scratch, then Save so Atlas can learn.";
  }
  if (module === "parlay") {
    return "Did this parlay hit? Select the result, then Save — Atlas uses it to improve future picks.";
  }
  if (module === "stock") {
    return "Closed this position? Select Win / Loss / Scratch, then Save so Atlas can learn.";
  }
  return "How did this pick turn out? Select a result, then Save — Atlas learns from every grade.";
}

export function LogOutcomeButtons({
  module,
  signalId,
  signalSnapshot,
  compact = false,
  className = "",
  onLogged,
}: LogOutcomeButtonsProps) {
  const normalizedId = normalizeSignalId(signalId);
  const [entry, setEntry] = useState<OutcomeEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [draft, setDraft] = useState<Outcome | null>(null);
  const [returnPct, setReturnPct] = useState("");

  const loadOutcome = useCallback(async () => {
    try {
      const row = await getPerformanceOutcome(module, normalizedId);
      setEntry(row);
      if (row?.return_pct != null) {
        setReturnPct(String(row.return_pct));
      }
    } catch {
      /* non-fatal */
    }
  }, [module, normalizedId]);

  useEffect(() => {
    void loadOutcome();
  }, [loadOutcome]);

  async function save() {
    if (!draft) {
      setMessage("Select Win, Loss, or Scratch first");
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const returnVal =
        returnPct.trim() !== "" && Number.isFinite(Number(returnPct))
          ? Number(returnPct)
          : undefined;
      const saved = await logPerformanceOutcome({
        module,
        signalId: normalizedId,
        outcome: draft,
        returnPct: returnVal,
        resolutionSource: changing || (entry && entry.outcome !== "pending")
          ? "manual_edit"
          : "manual",
        signalSnapshot,
      });
      if (!saved) {
        setMessage("Could not save — sign in and try again");
        setLoading(false);
        return;
      }
      setEntry(saved);
      setChanging(false);
      setDraft(null);
      setMessage("Saved — Atlas learning updated. Future picks will use this result.");
      await onLogged?.();
      // Ensure learning rollup runs even if the API path skipped it.
      void syncAtlasLearningAfterOutcome();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backend not responding");
    }
    setLoading(false);
  }

  const graded = entry && entry.outcome !== "pending";
  const editing = changing || !graded;

  if (graded && !changing) {
    const auto = String(entry.resolution_source ?? "").startsWith("auto_");
    const color =
      entry.outcome === "win"
        ? "text-emerald-400"
        : entry.outcome === "loss"
          ? "text-red-400"
          : "text-muted";
    return (
      <div className={`text-xs ${className}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`font-semibold capitalize ${color}`}>
            {entry.outcome}
            {entry.return_pct != null
              ? ` (${entry.return_pct > 0 ? "+" : ""}${entry.return_pct}%)`
              : ""}
          </span>
          {auto && <span className="text-muted">· auto-graded</span>}
          {(entry.resolution_source === "manual" ||
            entry.resolution_source === "manual_edit") && (
            <span className="text-muted">· you</span>
          )}
          <button
            type="button"
            onClick={() => {
              setChanging(true);
              setDraft(
                entry.outcome === "win" ||
                  entry.outcome === "loss" ||
                  entry.outcome === "scratch"
                  ? entry.outcome
                  : null,
              );
              setReturnPct(entry.return_pct != null ? String(entry.return_pct) : "");
              setMessage(null);
            }}
            className="font-medium text-accent hover:underline"
          >
            Change result
          </button>
        </div>
        {message && <p className="mt-1.5 text-muted">{message}</p>}
      </div>
    );
  }

  const choiceBtn =
    "rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-50 transition-colors";
  const selected = (value: Outcome) =>
    draft === value
      ? "ring-2 ring-offset-1 ring-offset-background ring-accent/60 bg-accent/10"
      : "";

  return (
    <div className={className}>
      <p className="mb-1.5 text-xs text-muted">
        {changing
          ? "Select the corrected result, then Save — Atlas learning updates immediately."
          : moduleHint(module, compact)}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={() => setDraft("win")}
          aria-pressed={draft === "win"}
          className={`${choiceBtn} border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 ${selected("win")}`}
        >
          Win
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => setDraft("loss")}
          aria-pressed={draft === "loss"}
          className={`${choiceBtn} border-red-500/40 text-red-300 hover:bg-red-500/10 ${selected("loss")}`}
        >
          Loss
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => setDraft("scratch")}
          aria-pressed={draft === "scratch"}
          className={`${choiceBtn} border-border text-muted hover:bg-surface-hover ${selected("scratch")}`}
        >
          Push / scratch
        </button>
      </div>

      {(module === "options" || module === "stock" || module === "parlay") && editing && (
        <label className="mt-2 flex items-center gap-2 text-xs text-muted">
          <span className="shrink-0">Return %</span>
          <input
            type="number"
            step="0.1"
            value={returnPct}
            onChange={(e) => setReturnPct(e.target.value)}
            placeholder="optional"
            className="w-24 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
          />
        </label>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading || !draft}
          onClick={() => void save()}
          className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save result"}
        </button>
        {changing && (
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setChanging(false);
              setDraft(null);
              setMessage(null);
            }}
            className={`${choiceBtn} border-border text-muted hover:bg-surface-hover`}
          >
            Cancel
          </button>
        )}
      </div>
      {message && <p className="mt-1.5 text-xs text-muted">{message}</p>}
    </div>
  );
}
