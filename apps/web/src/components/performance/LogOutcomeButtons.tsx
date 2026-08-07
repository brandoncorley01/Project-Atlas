"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPerformanceOutcome,
  logPerformanceOutcome,
  syncAtlasLearningAfterOutcome,
} from "@/lib/performance-api";

type Outcome = "win" | "loss" | "scratch";

interface OutcomeEntry {
  outcome: string;
  resolution_source?: string | null;
  return_pct?: number | null;
  hold_duration_hours?: number | null;
}

interface LogOutcomeButtonsProps {
  module: "options" | "stock" | "sports" | "parlay";
  signalId: string;
  signalSnapshot?: Record<string, unknown>;
  /** Seed from parent history so Change/Save still works if outcome fetch fails. */
  initialOutcome?: OutcomeEntry | null;
  compact?: boolean;
  className?: string;
  /** Called after a successful grade/change so parents can refresh. */
  onLogged?: () => void | Promise<void>;
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function normalizeSignalId(signalId: string): string {
  const trimmed = signalId.trim();
  return UUID_RE.test(trimmed) ? trimmed.toLowerCase() : trimmed;
}

function moduleHint(module: LogOutcomeButtonsProps["module"], compact: boolean) {
  if (compact) return "Select Win / Loss / Scratch, then Save result";
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
  initialOutcome = null,
  compact = false,
  className = "",
  onLogged,
}: LogOutcomeButtonsProps) {
  const normalizedId = normalizeSignalId(signalId);
  const [entry, setEntry] = useState<OutcomeEntry | null>(initialOutcome);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [draft, setDraft] = useState<Outcome | null>(null);
  const [returnPct, setReturnPct] = useState(
    initialOutcome?.return_pct != null ? String(initialOutcome.return_pct) : "",
  );
  const [holdHours, setHoldHours] = useState(
    initialOutcome?.hold_duration_hours != null
      ? String(initialOutcome.hold_duration_hours)
      : "",
  );
  const changingRef = useRef(changing);
  changingRef.current = changing;

  const seedKey = `${initialOutcome?.outcome ?? ""}:${initialOutcome?.return_pct ?? ""}:${initialOutcome?.hold_duration_hours ?? ""}:${initialOutcome?.resolution_source ?? ""}`;

  useEffect(() => {
    if (!initialOutcome || changingRef.current) return;
    setEntry(initialOutcome);
    if (initialOutcome.return_pct != null) {
      setReturnPct(String(initialOutcome.return_pct));
    }
    if (initialOutcome.hold_duration_hours != null) {
      setHoldHours(String(initialOutcome.hold_duration_hours));
    }
  }, [seedKey]); // eslint-disable-line react-hooks/exhaustive-deps -- seed by value fingerprint

  const loadOutcome = useCallback(async () => {
    try {
      const row = await getPerformanceOutcome(module, normalizedId);
      if (changingRef.current) return;
      if (row) {
        setEntry(row);
        if (row.return_pct != null) {
          setReturnPct(String(row.return_pct));
        }
        if (row.hold_duration_hours != null) {
          setHoldHours(String(row.hold_duration_hours));
        }
      }
    } catch {
      /* keep seeded entry */
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
      const holdVal =
        holdHours.trim() !== "" && Number.isFinite(Number(holdHours))
          ? Number(holdHours)
          : undefined;
      const saved = await logPerformanceOutcome({
        module,
        signalId: normalizedId,
        outcome: draft,
        returnPct: returnVal,
        holdDurationHours: holdVal,
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
              setHoldHours(
                entry.hold_duration_hours != null ? String(entry.hold_duration_hours) : "",
              );
              setMessage(null);
            }}
            className="rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1 font-semibold text-accent hover:bg-accent/20"
          >
            Change result
          </button>
        </div>
        {message && <p className="mt-1.5 text-muted">{message}</p>}
      </div>
    );
  }

  const choiceBtn =
    "rounded-md border px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 transition-colors";
  const selected = (value: Outcome) =>
    draft === value
      ? "ring-2 ring-offset-1 ring-offset-background ring-accent/60 bg-accent/10"
      : "";

  return (
    <div className={`min-w-[12rem] ${className}`}>
      <p className="mb-1.5 text-xs text-muted">
        {changing
          ? "Select the corrected result, then Save — Atlas learning updates immediately."
          : moduleHint(module, compact)}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={() => {
            setDraft("win");
            setMessage(null);
          }}
          aria-pressed={draft === "win"}
          className={`${choiceBtn} border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 ${selected("win")}`}
        >
          Win
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => {
            setDraft("loss");
            setMessage(null);
          }}
          aria-pressed={draft === "loss"}
          className={`${choiceBtn} border-red-500/40 text-red-300 hover:bg-red-500/10 ${selected("loss")}`}
        >
          Loss
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => {
            setDraft("scratch");
            setMessage(null);
          }}
          aria-pressed={draft === "scratch"}
          className={`${choiceBtn} border-border text-muted hover:bg-surface-hover ${selected("scratch")}`}
        >
          Push / scratch
        </button>
      </div>

      {editing && (
        <div className="mt-2 flex flex-wrap gap-3">
          <label className="flex items-center gap-2 text-xs text-muted">
            <span className="shrink-0">Return %</span>
            <input
              type="number"
              step="0.1"
              value={returnPct}
              onChange={(e) => setReturnPct(e.target.value)}
              placeholder={module === "sports" ? "e.g. +150" : "optional"}
              className="w-24 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
            />
          </label>
          {(module === "options" || module === "stock") && (
            <label className="flex items-center gap-2 text-xs text-muted">
              <span className="shrink-0">Hold hrs</span>
              <input
                type="number"
                step="0.5"
                value={holdHours}
                onChange={(e) => setHoldHours(e.target.value)}
                placeholder="optional"
                className="w-20 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
          )}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={loading || !draft}
          onClick={() => void save()}
          className={
            draft
              ? "rounded-md bg-accent px-4 py-2 text-xs font-bold text-white shadow-sm hover:opacity-90 disabled:opacity-50"
              : "rounded-md border border-dashed border-border px-4 py-2 text-xs font-semibold text-muted disabled:opacity-60"
          }
        >
          {loading ? "Saving…" : draft ? "Save result" : "Save result (pick one first)"}
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
