"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { usesBffProxy } from "@/lib/api-url";
import {
  fetchSportsIntelligence,
  refreshSportsIntelligence,
  type AtlasIntelligencePayload,
} from "@/lib/sports-intelligence-api";

interface AnalystPickSectionProps {
  signalId: string;
  atlasSelection: string;
}

type SupportingAnalyst = NonNullable<AtlasIntelligencePayload["supporting_analysts"]>[number];

async function getAccessToken(): Promise<string | undefined> {
  if (usesBffProxy()) {
    try {
      const supabase = createClient();
      const session = await supabase.auth.getSession();
      return session.data.session?.access_token;
    } catch {
      return undefined;
    }
  }
  const supabase = createClient();
  const session = await supabase.auth.getSession();
  return session.data.session?.access_token;
}

/**
 * Standalone "Analyst backing" block — always visible under Ask Atlas.
 * Lists public sources that support Atlas's selection.
 */
export function AnalystPickSection({ signalId, atlasSelection }: AnalystPickSectionProps) {
  const [supporters, setSupporters] = useState<SupportingAnalyst[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(
    async (forceRefresh = false) => {
      if (forceRefresh) setRefreshing(true);
      else setLoading(true);
      setMessage(null);
      try {
        const token = await getAccessToken();
        if (!usesBffProxy() && !token) {
          setSupporters([]);
          setMessage("Sign in to load analyst backing for this pick.");
          return;
        }

        let payload = await fetchSportsIntelligence(signalId, token);
        if (!payload) {
          setSupporters([]);
          setMessage("Analyst layer unavailable for this pick right now.");
          return;
        }
        if (!payload.enabled) {
          setSupporters([]);
          setMessage(
            "Analyst backing is off on the API. Set ATLAS_EXPERT_INTELLIGENCE_ENABLED=true on Render, then rescan.",
          );
          return;
        }

        if (forceRefresh || payload.status === "empty") {
          try {
            payload = await refreshSportsIntelligence(signalId, token);
          } catch (err) {
            if (!forceRefresh) {
              // Keep empty state if first auto-refresh fails (e.g. migration missing).
              setSupporters([]);
              setMessage(
                err instanceof Error
                  ? err.message
                  : "Could not pull analyst sources yet. Tap Refresh to retry.",
              );
              return;
            }
            throw err;
          }
        }

        const list =
          payload.supporting_analysts?.filter(Boolean) ??
          payload.analyst_cards?.filter((c) => c.supports_atlas) ??
          [];
        setSupporters(list.slice(0, 6));
        if (list.length === 0) {
          setMessage(
            `No public sources found backing ${atlasSelection} yet. Atlas still ranks on market edge and form.`,
          );
        }
      } catch (err) {
        setSupporters([]);
        setMessage(err instanceof Error ? err.message : "Could not load analyst backing.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [atlasSelection, signalId],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  return (
    <section
      aria-label="Analyst backing"
      className="mt-4 overflow-hidden rounded-2xl border-2 border-emerald-400/40 bg-gradient-to-b from-emerald-500/15 to-emerald-500/5 shadow-[0_0_0_1px_rgba(52,211,153,0.12)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-emerald-400/25 bg-emerald-500/10 px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-300">
            Analyst backing
          </p>
          <h3 className="mt-1 text-base font-semibold text-foreground sm:text-lg">
            Who supports this Atlas pick
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Public outlets and analysts aligned with{" "}
            <span className="font-semibold text-emerald-100">{atlasSelection}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load(true)}
          disabled={loading || refreshing}
          className="shrink-0 rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-1.5 text-xs font-semibold text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh sources"}
        </button>
      </div>

      <div className="px-4 py-3">
        {(loading || refreshing) && supporters.length === 0 && (
          <p className="text-sm text-muted">
            {refreshing ? "Pulling analyst sources…" : "Loading analyst backing…"}
          </p>
        )}

        {!loading && message && supporters.length === 0 && (
          <p className="text-sm leading-relaxed text-muted">{message}</p>
        )}

        {supporters.length > 0 && (
          <ul className="space-y-3">
            {supporters.map((card, idx) => (
              <li
                key={`${card.source}-${card.url ?? idx}`}
                className="rounded-xl border border-border/60 bg-background/50 px-3.5 py-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">
                    {card.analyst || card.source}
                    {card.analyst && card.source && card.analyst !== card.source ? (
                      <span className="font-normal text-muted"> · {card.source}</span>
                    ) : null}
                  </p>
                  {card.pick && (
                    <span className="rounded-md bg-emerald-500/20 px-2 py-0.5 text-[11px] font-bold text-emerald-200">
                      {card.pick}
                    </span>
                  )}
                </div>
                {(card.title || card.reasoning?.[0]) && (
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">
                    {card.title || card.reasoning?.[0]}
                  </p>
                )}
                {card.url && (
                  <a
                    href={card.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
                  >
                    View source →
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
