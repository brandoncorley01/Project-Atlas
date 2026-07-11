"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { usesBffProxy } from "@/lib/api-url";

type ModuleKind = "options" | "stock" | "sports";

interface AtlasModuleInsightProps {
  module: ModuleKind;
  signalId?: string | null;
  headline?: string;
  urgencyNote?: string | null;
  href?: string;
}

interface ExplainResponse {
  explanation?: string;
  why_atlas?: string;
  pick_thesis?: string;
  bullets?: string[];
}

/**
 * Compact Atlas Insight strip for Stocks / Options — mirrors Sports intelligence
 * without duplicating the full sports command center.
 */
export function AtlasModuleInsight({
  module,
  signalId,
  headline,
  urgencyNote,
  href,
}: AtlasModuleInsightProps) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!signalId) {
      setText(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        let token: string | undefined;
        if (!usesBffProxy()) {
          const { data } = await createClient().auth.getSession();
          token = data.session?.access_token ?? undefined;
        }
        const body = await apiFetch<ExplainResponse>("/ai/explain", token, {
          method: "POST",
          body: JSON.stringify({ module, signal_id: signalId }),
          timeoutMs: module === "options" ? 55_000 : 35_000,
        });
        if (cancelled) return;
        const thesis =
          body.pick_thesis ||
          body.why_atlas ||
          body.explanation ||
          (body.bullets?.length ? body.bullets.slice(0, 2).join(" · ") : null);
        setText(thesis ? String(thesis).slice(0, 320) : null);
      } catch {
        if (!cancelled) setText(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [module, signalId]);

  const title =
    module === "options"
      ? "Atlas Insight · Options"
      : module === "stock"
        ? "Atlas Insight · Stocks"
        : "Atlas Insight";

  return (
    <section className="mb-5 rounded-xl border border-sky-500/25 bg-sky-500/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/90">{title}</p>
          <p className="mt-1 text-sm font-medium text-foreground">
            {headline ||
              (module === "options"
                ? "Near-term premium moves faster — prioritize catalysts and DTE."
                : "Swing setups ranked by technicals + catalysts.")}
          </p>
        </div>
        {href && (
          <Link href={href} className="text-xs font-semibold text-sky-200 hover:underline">
            Open board →
          </Link>
        )}
      </div>
      {urgencyNote && (
        <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100">
          {urgencyNote}
        </p>
      )}
      <p className="mt-2 text-xs leading-relaxed text-muted">
        {loading
          ? "Reading the top ranked setup…"
          : text ||
            "Scan to populate ranked picks — Atlas will surface a thesis on the #1 opportunity."}
      </p>
    </section>
  );
}
