"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ParlayCard, type Parlay } from "@/components/parlays/ParlayCard";
import { SportsEventSearch, type ParlayLegSignal } from "@/components/sports/SportsEventSearch";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { apiFetch } from "@/lib/api";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import { createClient } from "@/lib/supabase/client";

interface SportsPick {
  id: string;
  title?: string;
  sport?: string;
  event_name?: string;
  selection?: string;
  bet_type?: string;
  odds_american?: number;
  opportunity_score?: number;
}

interface ParlayEditorProps {
  initialParlay: Parlay;
}

export function ParlayEditor({ initialParlay }: ParlayEditorProps) {
  const [parlay, setParlay] = useState(initialParlay);
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    (initialParlay.legs ?? [])
      .map((leg) => leg.sports_signal_id)
      .filter((id): id is string => Boolean(id)),
  );
  const [pool, setPool] = useState<SportsPick[]>([]);
  const [preview, setPreview] = useState<Parlay | null>(null);
  const [loadingPool, setLoadingPool] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  // Resolve leg signal IDs from pool when DB legs lack sports_signal_id (older parlays).
  useEffect(() => {
    if (!pool.length || !(parlay.legs?.length ?? 0)) return;
    const needsResolve = (parlay.legs ?? []).some((leg) => !leg.sports_signal_id);
    if (!needsResolve) return;

    const resolved = (parlay.legs ?? [])
      .map((leg) => {
        if (leg.sports_signal_id) return leg.sports_signal_id;
        const match = pool.find(
          (p) =>
            p.event_name === leg.event_name &&
            p.selection === leg.selection &&
            (p.bet_type ?? "moneyline") === (leg.bet_type ?? "moneyline"),
        );
        return match?.id ?? null;
      })
      .filter((id): id is string => Boolean(id));

    if (resolved.length >= 2) {
      setSelectedIds(resolved);
    }
  }, [pool, parlay.legs]);

  const dirty = useMemo(() => {
    const current = (parlay.legs ?? [])
      .map((leg) => leg.sports_signal_id)
      .filter((id): id is string => Boolean(id));
    if (current.length !== selectedIds.length) return true;
    return current.some((id, idx) => id !== selectedIds[idx]);
  }, [parlay.legs, selectedIds]);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  const loadPool = useCallback(async () => {
    setLoadingPool(true);
    try {
      const token = await getToken();
      const res = await fetch(`${getApiUrl()}/signals/sports?limit=60&window=week`, {
        headers: apiRequestHeaders(token),
        cache: "no-store",
        credentials: usesBffProxy() ? "include" : "same-origin",
      });
      if (res.ok) {
        const data = await res.json();
        setPool((data.items ?? []) as SportsPick[]);
      }
    } finally {
      setLoadingPool(false);
    }
  }, []);

  useEffect(() => {
    void loadPool();
  }, [loadPool]);

  useEffect(() => {
    if (!editing || selectedIds.length < 2) {
      setPreview(null);
      return;
    }
    if (!dirty) {
      setPreview(null);
      return;
    }

    let cancelled = false;
    async function calc() {
      setCalculating(true);
      setError(null);
      try {
        const token = await getToken();
        const result = await apiFetch<{ parlay: Parlay }>("/parlays/calculate", token, {
          method: "POST",
          body: JSON.stringify({ signal_ids: selectedIds }),
          timeoutMs: 20_000,
        });
        if (!cancelled) setPreview(result.parlay);
      } catch (err) {
        if (!cancelled) {
          setPreview(null);
          setError(err instanceof Error ? err.message : "Could not calculate parlay");
        }
      } finally {
        if (!cancelled) setCalculating(false);
      }
    }
    void calc();
    return () => {
      cancelled = true;
    };
  }, [editing, selectedIds, dirty]);

  function toggleLeg(pick: SportsPick) {
    setSelectedIds((prev) => {
      if (prev.includes(pick.id)) return prev.filter((x) => x !== pick.id);
      if (prev.length >= 6) return prev;
      const takenEvents = new Set(
        pool
          .filter((p) => prev.includes(p.id))
          .map((p) => p.event_name)
          .filter(Boolean),
      );
      if (pick.event_name && takenEvents.has(pick.event_name)) {
        setError("Only one leg per event — pick a different game.");
        return prev;
      }
      setError(null);
      return [...prev, pick.id];
    });
    setMessage(null);
  }

  function addFanDuelLeg(leg: ParlayLegSignal) {
    setEditing(true);
    setPool((prev) => {
      if (prev.some((p) => p.id === leg.id)) return prev;
      return [
        {
          id: leg.id,
          sport: leg.sport,
          event_name: leg.event_name,
          selection: leg.selection,
          bet_type: leg.bet_type,
          odds_american: leg.odds_american,
        },
        ...prev,
      ];
    });
    setSelectedIds((prev) => {
      if (prev.includes(leg.id)) {
        setMessage("That FanDuel leg is already on this parlay.");
        return prev;
      }
      if (prev.length >= 6) {
        setError("Parlays max out at 6 legs.");
        return prev;
      }
      const existingEvents = new Set(
        pool.filter((p) => prev.includes(p.id)).map((p) => p.event_name).filter(Boolean),
      );
      if (leg.event_name && existingEvents.has(leg.event_name)) {
        setError("Only one FanDuel leg per event — pick a different game.");
        return prev;
      }
      setError(null);
      setMessage(`Added FanDuel leg: ${leg.selection}`);
      return [...prev, leg.id];
    });
  }

  async function saveParlay() {
    if (selectedIds.length < 2) {
      setError("Select at least 2 legs from different events.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const token = await getToken();
      const result = await apiFetch<{ parlay: Parlay }>(`/parlays/${parlay.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ signal_ids: selectedIds }),
        timeoutMs: 25_000,
      });
      setParlay(result.parlay);
      setSelectedIds(
        (result.parlay.legs ?? [])
          .map((leg) => leg.sports_signal_id)
          .filter((id): id is string => Boolean(id)),
      );
      setPreview(null);
      setEditing(false);
      setMessage("Parlay updated with new legs and recalculated odds.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save parlay");
    } finally {
      setSaving(false);
    }
  }

  const display = preview ?? parlay;

  return (
    <div className="space-y-6">
      <ParlayCard row={display} rank={1} />

      <section className="rounded-xl border border-border bg-surface p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Edit parlay legs</h2>
            <p className="mt-1 text-xs text-muted">
              Search FanDuel markets or pick from Atlas sports plays (2–6 legs, one per event).
              Odds and scores recalculate on save.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setEditing((v) => !v);
              setError(null);
              setMessage(null);
              if (editing) {
                setSelectedIds(
                  (parlay.legs ?? [])
                    .map((leg) => leg.sports_signal_id)
                    .filter((id): id is string => Boolean(id)),
                );
                setPreview(null);
              }
            }}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-accent/50"
          >
            {editing ? "Cancel editing" : "Modify legs"}
          </button>
        </div>

        {editing && (
          <>
            <div className="mt-4">
              <SportsEventSearch intent="parlay" onParlayLegAdded={addFanDuelLeg} />
            </div>

            <p className="mt-3 text-xs text-muted">
              {selectedIds.length} leg{selectedIds.length !== 1 ? "s" : ""} selected
              {selectedIds.length < 2 && " — pick at least 2"}
            </p>

            {loadingPool ? (
              <p className="mt-4 text-sm text-muted">Loading available plays…</p>
            ) : (
              <div className="mt-4 max-h-80 space-y-2 overflow-y-auto">
                {pool.map((pick) => {
                  const selected = selectedIds.includes(pick.id);
                  return (
                    <button
                      key={pick.id}
                      type="button"
                      onClick={() => toggleLeg(pick)}
                      className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors ${
                        selected
                          ? "border-orange-500/50 bg-orange-500/10"
                          : "border-border bg-background/50 hover:border-orange-500/30"
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-xs font-bold ${
                          selected
                            ? "border-orange-500 bg-orange-500 text-white"
                            : "border-border text-muted"
                        }`}
                      >
                        {selected ? "✓" : "+"}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{pick.selection}</span>
                        <span className="mt-0.5 block text-xs text-muted">
                          {pick.sport} · {pick.bet_type} · {pick.event_name}
                        </span>
                      </span>
                      {pick.opportunity_score != null && (
                        <ScoreBadge
                          label="Opp."
                          shortLabel="Opp."
                          value={pick.opportunity_score}
                          variant="opportunity"
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {preview && (
              <div className="mt-4 rounded-lg border border-fanduel/30 bg-fanduel-muted/30 p-3 text-sm">
                <p className="text-xs font-semibold uppercase text-muted">Preview</p>
                <p className="mt-1 font-medium text-fanduel-text">
                  FanDuel {preview.combined_odds_american > 0 ? "+" : ""}
                  {preview.combined_odds_american} · {Number(preview.combined_odds_decimal).toFixed(2)}x
                </p>
                {preview.correlation_warning && (
                  <p className="mt-2 text-xs text-amber-200">{preview.correlation_warning}</p>
                )}
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void saveParlay()}
                disabled={saving || calculating || selectedIds.length < 2 || !dirty}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save parlay changes"}
              </button>
              {calculating && <span className="self-center text-xs text-muted">Calculating…</span>}
            </div>
          </>
        )}

        {message && <p className="mt-3 text-sm text-success">{message}</p>}
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      </section>
    </div>
  );
}
