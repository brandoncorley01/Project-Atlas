"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

type Outcome = "win" | "loss" | "scratch";

interface LogOutcomeButtonsProps {
  module: "options" | "stock" | "sports" | "parlay";
  signalId: string;
  compact?: boolean;
  className?: string;
}

interface OutcomeEntry {
  outcome: string;
  resolution_source?: string | null;
  return_pct?: number | null;
}

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

export function LogOutcomeButtons({
  module,
  signalId,
  compact = false,
  className = "",
}: LogOutcomeButtonsProps) {
  const [entry, setEntry] = useState<OutcomeEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadOutcome = useCallback(async () => {
    const token = await getToken();
    try {
      const params = new URLSearchParams({ module, signal_id: signalId });
      const res = await fetch(`${getApiUrl()}/performance/outcome?${params}`, {
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      if (res.ok) {
        const data = await res.json();
        setEntry(data.outcome ?? null);
      }
    } catch {
      /* non-fatal */
    }
  }, [module, signalId]);

  useEffect(() => {
    void loadOutcome();
  }, [loadOutcome]);

  async function log(outcome: Outcome) {
    setLoading(true);
    setMessage(null);
    const token = await getToken();
    try {
      const res = await fetch(`${getApiUrl()}/performance`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        body: JSON.stringify({ module, signal_id: signalId, outcome }),
      });
      const body = await res.json();
      if (!res.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Could not log");
        setLoading(false);
        return;
      }
      setEntry(body.entry);
      setMessage("Logged — Atlas will use this to improve future picks");
      window.dispatchEvent(new Event("atlas:performance-updated"));
    } catch {
      setMessage("Backend not responding");
    }
    setLoading(false);
  }

  if (entry && entry.outcome !== "pending") {
    const auto = entry.resolution_source === "auto_sports";
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
