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

interface ExplainResponse {
  explanation?: string;
  bullets?: string[];
  risks?: string[];
  source?: string;
}

export function AtlasExplainButton({ module, signalId, className }: AtlasExplainButtonProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadExplanation() {
    if (data && open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (data) return;

    setLoading(true);
    setError(null);
    try {
      let token: string | undefined;
      if (!usesBffProxy()) {
        const { data: session } = await createClient().auth.getSession();
        token = session.session?.access_token;
      }
      const result = await apiFetch<ExplainResponse>("/ai/explain", token, {
        method: "POST",
        body: JSON.stringify({ module, signal_id: signalId }),
        timeoutMs: 25_000,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load explanation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => void loadExplanation()}
        disabled={loading}
        className="text-xs font-medium text-sky-300 hover:text-sky-200 hover:underline disabled:opacity-50"
      >
        {loading ? "Atlas is thinking…" : open && data ? "Hide Atlas insight" : "Ask Atlas for deeper insight"}
      </button>

      {open && (
        <div className="mt-3 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
          {loading && <p className="text-sm text-muted">Building explanation from scan data…</p>}
          {error && <p className="text-sm text-danger">{error}</p>}
          {data && !loading && (
            <>
              {data.source === "openai" && (
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-sky-200/70">
                  AI insight
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
