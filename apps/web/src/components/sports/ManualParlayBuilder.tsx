"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { usesBffProxy } from "@/lib/api-url";
import {
  calculateParlayLocally,
  formatParlayTicket,
  legFromSignal,
  payoutFromStake,
  type ParlayLegInput,
} from "@/lib/parlay-math";
import { parlayMetadata } from "@/lib/watchlist-api";

interface ManualParlayBuilderProps {
  signals: SportsSignal[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onClear: () => void;
}

export function ManualParlayBuilder({
  signals,
  selectedIds,
  onToggle,
  onClear,
}: ManualParlayBuilderProps) {
  const [stake, setStake] = useState(10);
  const [copied, setCopied] = useState(false);
  const [savingParlay, setSavingParlay] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const router = useRouter();

  const selectedLegs: ParlayLegInput[] = useMemo(() => {
    return signals.filter((s) => selectedIds.has(s.id)).map(legFromSignal);
  }, [signals, selectedIds]);

  const calculated = useMemo(
    () => (selectedLegs.length >= 2 ? calculateParlayLocally(selectedLegs) : null),
    [selectedLegs],
  );

  const payout = calculated ? payoutFromStake(stake, calculated.combined_odds_decimal) : null;

  const parlaySave = calculated
    ? parlayMetadata({
        ...calculated,
        source: "manual",
        stake,
        legs: calculated.legs,
      })
    : null;

  async function copyTicket() {
    if (!calculated) return;
    await navigator.clipboard.writeText(formatParlayTicket(calculated));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function saveToParlays() {
    if (!calculated || selectedLegs.length < 2) return;
    setSavingParlay(true);
    setSaveMessage(null);
    try {
      let token: string | undefined;
      if (!usesBffProxy()) {
        const { data } = await createClient().auth.getSession();
        token = data.session?.access_token;
      }
      const result = await apiFetch<{ parlay: { id: string } }>("/parlays", token, {
        method: "POST",
        body: JSON.stringify({ signal_ids: selectedLegs.map((l) => l.id) }),
        timeoutMs: 25_000,
      });
      setSaveMessage("Parlay saved — you can edit legs anytime.");
      router.push(`/parlays/${result.parlay.id}`);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Could not save parlay");
    } finally {
      setSavingParlay(false);
    }
  }

  if (selectedIds.size === 0) return null;

  return (
    <div className="sticky bottom-20 z-30 mb-6 rounded-xl border border-orange-500/40 bg-surface/95 p-4 shadow-xl shadow-orange-500/10 backdrop-blur-md md:bottom-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-orange-300">
            Parlay builder · {selectedIds.size} leg{selectedIds.size !== 1 ? "s" : ""} selected
          </p>
          <p className="mt-0.5 text-xs text-muted">
            Pick 2–6 plays from different events · tap cards to add/remove legs
          </p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-muted hover:text-foreground"
        >
          Clear all
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {selectedLegs.map((leg) => (
          <button
            key={leg.id}
            type="button"
            onClick={() => onToggle(leg.id)}
            className="rounded-full border border-orange-500/30 bg-orange-500/10 px-2.5 py-1 text-xs text-orange-200 hover:bg-orange-500/20"
          >
            {leg.selection} ×
          </button>
        ))}
      </div>

      {selectedLegs.length < 2 && (
        <p className="mt-3 text-sm text-muted">Select at least one more leg to calculate combined odds.</p>
      )}

      {calculated && (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-fanduel/30 bg-fanduel-muted px-3 py-2">
              <p className="text-[10px] uppercase text-muted">FanDuel combined</p>
              <p className="text-lg font-bold text-fanduel-text">
                {calculated.combined_odds_american > 0 ? "+" : ""}
                {calculated.combined_odds_american}
              </p>
              <p className="text-xs text-muted">{calculated.combined_odds_decimal.toFixed(2)}x</p>
            </div>
            <ScoreBadge label="Opportunity" value={calculated.opportunity_score} variant="opportunity" />
            <ScoreBadge label="Confidence" value={calculated.confidence_score} variant="confidence" />
            <ScoreBadge label="Risk" value={calculated.risk_score} variant="risk" />
          </div>

          {calculated.correlation_warning && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              {calculated.correlation_warning}
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted">Stake ($)</span>
              <input
                type="number"
                min={1}
                step={1}
                value={stake}
                onChange={(e) => setStake(Math.max(1, Number(e.target.value) || 1))}
                className="w-24 rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
              />
            </label>
            {payout && (
              <div className="text-sm">
                <p className="text-xs text-muted">Potential return</p>
                <p className="font-bold text-success">${payout.totalReturn.toFixed(2)}</p>
                <p className="text-xs text-muted">Profit ${payout.profit.toFixed(2)}</p>
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {parlaySave && (
              <AddToWatchlistButton
                symbol={parlaySave.symbol}
                itemType="parlay"
                metadata={parlaySave.metadata}
                label="Save parlay to watchlist"
                variant="primary"
              />
            )}
            <button
              type="button"
              onClick={() => void saveToParlays()}
              disabled={savingParlay}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {savingParlay ? "Saving…" : "Save & edit parlay"}
            </button>
            <button
              type="button"
              onClick={copyTicket}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-accent/50"
            >
              {copied ? "Copied!" : "Copy ticket"}
            </button>
            <Link
              href="/watchlist?tab=parlays"
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted hover:text-foreground"
            >
              View saved parlays →
            </Link>
          </div>
          {saveMessage && <p className="mt-2 text-xs text-muted">{saveMessage}</p>}
        </>
      )}
    </div>
  );
}

/** Checkbox overlay for sports cards in parlay selection mode */
export function ParlayLegToggle({
  signalId,
  selected,
  onToggle,
}: {
  signalId: string;
  selected: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle(signalId);
      }}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-sm font-bold transition-colors ${
        selected
          ? "border-orange-500 bg-orange-500 text-white"
          : "border-border bg-background text-muted hover:border-orange-500/50"
      }`}
      title={selected ? "Remove from parlay" : "Add to parlay"}
      aria-pressed={selected}
    >
      {selected ? "✓" : "+"}
    </button>
  );
}
