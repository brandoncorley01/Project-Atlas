"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  fetchSportsIntelligence,
  refreshSportsIntelligence,
  type AtlasIntelligencePayload,
} from "@/lib/sports-intelligence-api";

interface AnalystPickSectionProps {
  signalId: string;
  atlasSelection: string;
  enabled?: boolean;
}

type SupportingAnalyst = NonNullable<AtlasIntelligencePayload["supporting_analysts"]>[number];

/**
 * Compact "Analyst picks" strip under each sports card.
 * Only shows outlets/analysts that support Atlas's selection.
 */
export function AnalystPickSection({
  signalId,
  atlasSelection,
  enabled = true,
}: AnalystPickSectionProps) {
  const [supporters, setSupporters] = useState<SupportingAnalyst[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState<"idle" | "empty" | "ready" | "off">("idle");

  const load = useCallback(async () => {
    if (!enabled) {
      setStatus("off");
      return;
    }
    setLoading(true);
    try {
      const supabase = createClient();
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) {
        setStatus("off");
        return;
      }
      let payload = await fetchSportsIntelligence(signalId, token);
      if (!payload?.enabled) {
        setStatus("off");
        return;
      }
      // First open with no cache — pull sources once so the section can fill.
      if (payload.status === "empty") {
        setRefreshing(true);
        try {
          payload = await refreshSportsIntelligence(signalId, token);
        } finally {
          setRefreshing(false);
        }
      }
      const list =
        payload.supporting_analysts?.filter(Boolean) ??
        payload.analyst_cards?.filter((c) => c.supports_atlas) ??
        [];
      setSupporters(list.slice(0, 4));
      setStatus(list.length > 0 ? "ready" : "empty");
    } catch {
      setStatus("empty");
      setSupporters([]);
    } finally {
      setLoading(false);
    }
  }, [enabled, signalId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!enabled || status === "off") return null;

  return (
    <div className="mt-4 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">
            Analyst picks
          </p>
          <p className="mt-0.5 text-[11px] text-muted">
            Public sources backing Atlas on <span className="font-medium text-foreground">{atlasSelection}</span>
          </p>
        </div>
        {(loading || refreshing) && (
          <span className="text-[11px] text-muted">
            {refreshing ? "Pulling sources…" : "Loading…"}
          </span>
        )}
      </div>

      {!loading && status === "empty" && (
        <p className="mt-2 text-xs text-muted">
          No matching analyst support found yet for this side. Atlas still ranks on market edge and form.
        </p>
      )}

      {supporters.length > 0 && (
        <ul className="mt-3 space-y-2">
          {supporters.map((card, idx) => (
            <li
              key={`${card.source}-${card.url ?? idx}`}
              className="rounded-lg border border-border/50 bg-background/40 px-3 py-2"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-xs font-semibold text-foreground">
                  {card.analyst || card.source}
                  {card.analyst && card.source && card.analyst !== card.source ? (
                    <span className="font-normal text-muted"> · {card.source}</span>
                  ) : null}
                </p>
                {card.pick && (
                  <span className="rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-200">
                    {card.pick}
                  </span>
                )}
              </div>
              {(card.title || card.reasoning?.[0]) && (
                <p className="mt-1 text-xs text-muted line-clamp-2">
                  {card.title || card.reasoning?.[0]}
                </p>
              )}
              {card.url && (
                <a
                  href={card.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-[11px] font-medium text-accent hover:underline"
                >
                  View source
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
