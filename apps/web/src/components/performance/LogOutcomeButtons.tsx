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

export function LogOutcomeButtons({
  module,
  signalId,
  signalSnapshot,
  compact = false,
  className = "",
}: LogOutcomeButtonsProps) {
  const normalizedId = normalizeSignalId(signalId);
  const [entry, setEntry] = useState<OutcomeEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
        resolutionSource: "manual",
        signalSnapshot,
      });
      if (!saved) {
        setMessage("Could not log — sign in and try again");
        setLoading(false);
        return;
      }
      setEntry(saved);
      setMessage("Logged — Atlas will use this to improve future picks");
      window.dispatchEvent(new Event("atlas:performance-updated"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backend not responding");
    }
    setLoading(false);
  }

  if (entry && entry.outcome !== "pending") {
    const auto = String(entry.resolution_source ?? "").startsWith("auto_");
    const color =
      entry.outcome === "win"
        ? "text-emerald-400"
        : entry.outcome === "loss"
          ? "text-red-400"
          : "text-muted";
    return (
      <div className={`text-xs ${className}`}>
        <span className={`font-semibold capitalize ${color}`}>
          {entry.outcome}
          {entry.return_pct != null ? ` (${entry.return_pct > 0 ? "+" : ""}${entry.return_pct}%)` : ""}
        </span>
        {auto && <span className="ml-2 text-muted">· auto-graded</span>}
        {!auto && entry.resolution_source === "manual" && (
          <span className="ml-2 text-muted">· saved</span>
        )}
      </div>
    );
  }

  const btn =
    "rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-50 transition-colors";
  return (
    <div className={className}>
      <p className="mb-1.5 text-xs text-muted">
        {compact ? "Result?" : "How did this pick turn out? Atlas learns from your results."}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={() => log("win")}
          className={`${btn} border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10`}
        >
          Win
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => log("loss")}
          className={`${btn} border-red-500/40 text-red-300 hover:bg-red-500/10`}
        >
          Loss
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => log("scratch")}
          className={`${btn} border-border text-muted hover:bg-surface-hover`}
        >
          Push / scratch
        </button>
      </div>
      {message && <p className="mt-1.5 text-xs text-muted">{message}</p>}
    </div>
  );
}
