"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SportsEventSearch, type ParlayLegSignal } from "@/components/sports/SportsEventSearch";
import { apiFetch } from "@/lib/api";
import { usesBffProxy } from "@/lib/api-url";
import { createClient } from "@/lib/supabase/client";
import {
  calculateParlayLocally,
  type ParlayLegInput,
} from "@/lib/parlay-math";

function toInput(leg: ParlayLegSignal): ParlayLegInput {
  return {
    id: leg.id,
    sport: leg.sport || "Sports",
    event_name: leg.event_name,
    bet_type: leg.bet_type || "moneyline",
    selection: leg.selection,
    odds_american: leg.odds_american,
    event_start: leg.event_start ?? null,
  };
}

export function ParlayFanDuelBuilder() {
  const router = useRouter();
  const [legs, setLegs] = useState<ParlayLegSignal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const calculated = useMemo(() => {
    if (legs.length < 2) return null;
    return calculateParlayLocally(legs.map(toInput));
  }, [legs]);

  function addLeg(leg: ParlayLegSignal) {
    setError(null);
    setMessage(null);
    setLegs((prev) => {
      if (prev.some((l) => l.id === leg.id)) {
        setMessage("That leg is already on this parlay.");
        return prev;
      }
      if (prev.length >= 6) {
        setError("Parlays max out at 6 legs.");
        return prev;
      }
      if (prev.some((l) => l.event_name && l.event_name === leg.event_name)) {
        setError("Only one FanDuel leg per event — pick a different game.");
        return prev;
      }
      setMessage(`Added ${leg.selection} · FanDuel ${leg.odds_american > 0 ? "+" : ""}${leg.odds_american}`);
      return [...prev, leg];
    });
  }

  function removeLeg(id: string) {
    setLegs((prev) => prev.filter((l) => l.id !== id));
    setError(null);
    setMessage(null);
  }

  async function saveParlay() {
    if (legs.length < 2) {
      setError("Add at least 2 FanDuel legs from different events.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      let token: string | undefined;
      if (!usesBffProxy()) {
        const { data } = await createClient().auth.getSession();
        token = data.session?.access_token;
      }
      const result = await apiFetch<{ parlay: { id: string } }>("/parlays", token, {
        method: "POST",
        body: JSON.stringify({ signal_ids: legs.map((l) => l.id) }),
        timeoutMs: 25_000,
      });
      router.push(`/parlays/${result.parlay.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save parlay");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mb-8 space-y-4">
      <div className="rounded-xl border border-fanduel/40 bg-fanduel-muted/40 px-4 py-3">
        <p className="text-sm font-semibold text-fanduel-text">Build with FanDuel search</p>
        <p className="mt-1 text-xs text-muted">
          Search open FanDuel markets, add each leg to your ticket, then save. Atlas grades each
          leg when the games finish.
        </p>
      </div>

      <SportsEventSearch intent="parlay" onParlayLegAdded={addLeg} />

      {legs.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold">
                Your ticket · {legs.length} leg{legs.length !== 1 ? "s" : ""}
              </p>
              {calculated && (
                <p className="mt-1 text-sm text-fanduel-text">
                  FanDuel combined {calculated.combined_odds_american > 0 ? "+" : ""}
                  {calculated.combined_odds_american} ·{" "}
                  {Number(calculated.combined_odds_decimal).toFixed(2)}x
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  setLegs([]);
                  setError(null);
                  setMessage(null);
                }}
                className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-danger/40"
              >
                Clear
              </button>
              <button
                type="button"
                disabled={saving || legs.length < 2}
                onClick={() => void saveParlay()}
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save parlay"}
              </button>
            </div>
          </div>

          <ul className="mt-3 space-y-2">
            {legs.map((leg, idx) => (
              <li
                key={leg.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background/50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-wide text-muted">
                    Leg {idx + 1} · {leg.sport} · {leg.bet_type}
                  </p>
                  <p className="font-medium">{leg.selection}</p>
                  <p className="text-xs text-muted">{leg.event_name}</p>
                  <p className="mt-0.5 text-sm text-fanduel-text">
                    FanDuel {leg.odds_american > 0 ? "+" : ""}
                    {leg.odds_american}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeLeg(leg.id)}
                  className="shrink-0 text-xs text-muted hover:text-danger"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {message && <p className="text-sm text-success">{message}</p>}
      {error && <p className="text-sm text-danger">{error}</p>}
    </section>
  );
}
