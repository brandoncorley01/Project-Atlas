"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getPerformanceOutcome,
  logPerformanceOutcome,
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
      ? "Close / settle?"
      : "Result?";
  }
  if (module === "options") {
    return "Closed this options position? Log win/loss so Atlas can learn — you can change it later.";
  }
  if (module === "parlay") {
    return "Did this parlay hit? Log the result — you can change it later if a leg settles differently.";
  }
  if (module === "stock") {
    return "Closed this position? Log win/loss so Atlas can learn.";
  }
  return "How did this pick turn out? Atlas learns from your results.";
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

  const loadOutcome = useCallback(async () => {
    try {
      const row = await getPerformanceOutcome(module, normalizedId);
      setEntry(row);
    } catch {
      /* non-fatal */
    }
  }, [module, normalizedId]);

  useEffect(() => {
    void loadOutcome();
  }, [loadOutcome]);

  async function log(outcome: Outcome) {
    setLoading(true);
    setMessage(null);
    try {
      const saved = await logPerformanceOutcome({
        module,
        signalId: normalizedId,
        outcome,
        resolutionSource: changing ? "manual_edit" : "manual",
        signalSnapshot,
      });
      if (!saved) {
        setMessage("Could not log — sign in and try again");
        setLoading(false);
        return;
      }
      setEntry(saved);
      setChanging(false);
      setMessage(
        changing
          ? "Result updated — Atlas will use the new outcome"
          : "Logged — Atlas will use this to improve future picks",
      );
      window.dispatchEvent(new Event("atlas:performance-updated"));
      await onLogged?.();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backend not responding");
    }
    setLoading(false);
  }

  const graded = entry && entry.outcome !== "pending";

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

  const btn =
    "rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-50 transition-colors";
  return (
    <div className={className}>
      <p className="mb-1.5 text-xs text-muted">
        {changing
          ? module === "parlay" || module === "options"
            ? `Change this ${module === "parlay" ? "parlay" : "options"} result`
            : "Change the logged result"
          : moduleHint(module, compact)}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={() => void log("win")}
          className={`${btn} border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10`}
        >
          Win
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => void log("loss")}
          className={`${btn} border-red-500/40 text-red-300 hover:bg-red-500/10`}
        >
          Loss
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => void log("scratch")}
          className={`${btn} border-border text-muted hover:bg-surface-hover`}
        >
          Push / scratch
        </button>
        {changing && (
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setChanging(false);
              setMessage(null);
            }}
            className={`${btn} border-border text-muted hover:bg-surface-hover`}
          >
            Cancel
          </button>
        )}
      </div>
      {message && <p className="mt-1.5 text-xs text-muted">{message}</p>}
    </div>
  );
}
