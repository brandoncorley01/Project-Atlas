"use client";

import { useCallback, useState } from "react";
import { LogOutcomeButtons } from "@/components/performance/LogOutcomeButtons";
import { registerPerformanceForItem } from "@/lib/performance-api";
import type { PerformanceEntry } from "@/components/performance/PerformanceView";
import {
  performanceTrackingForItem,
  type WatchlistItem,
} from "@/lib/watchlist-types";

function statusKey(module: string, signalId: string) {
  return `${module}:${signalId.trim().toLowerCase()}`;
}

export function performanceStatusKey(item: WatchlistItem): string | null {
  const tracking = performanceTrackingForItem(item);
  if (!tracking) return null;
  return statusKey(tracking.module, tracking.signalId);
}

function StatusBadge({
  entry,
  trackable,
}: {
  entry: PerformanceEntry | null | undefined;
  trackable: boolean;
}) {
  if (!trackable) {
    return (
      <span className="rounded-full bg-background px-2 py-0.5 text-[10px] font-medium text-muted">
        Scan only
      </span>
    );
  }
  if (!entry) {
    return (
      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">
        Not in Performance
      </span>
    );
  }
  if (entry.outcome === "pending") {
    return (
      <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-medium text-sky-300">
        In Performance · awaiting grade
      </span>
    );
  }
  const color =
    entry.outcome === "win"
      ? "bg-emerald-500/15 text-emerald-300"
      : entry.outcome === "loss"
        ? "bg-red-500/15 text-red-300"
        : "bg-background text-muted";
  const auto = String(entry.resolution_source ?? "").startsWith("auto_");
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${color}`}>
      {entry.outcome}
      {entry.return_pct != null
        ? ` ${entry.return_pct > 0 ? "+" : ""}${entry.return_pct}%`
        : ""}
      {auto ? " · auto" : ""}
    </span>
  );
}

interface WatchlistPerformanceControlsProps {
  item: WatchlistItem;
  entry: PerformanceEntry | null | undefined;
  onRegistered: (entry: PerformanceEntry) => void;
}

export function WatchlistPerformanceControls({
  item,
  entry,
  onRegistered,
}: WatchlistPerformanceControlsProps) {
  const tracking = performanceTrackingForItem(item);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(async () => {
    if (!tracking) return;
    setSending(true);
    setError(null);
    try {
      const ok = await registerPerformanceForItem(item, { notify: true });
      if (!ok) {
        setError("Could not send — sign in and try again");
        setSending(false);
        return;
      }
      onRegistered({
        id: "",
        module: tracking.module,
        signal_id: tracking.signalId,
        outcome: "pending",
        resolution_source: "watchlist",
        signal_label:
          typeof item.metadata?.label === "string"
            ? item.metadata.label
            : item.symbol,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    }
    setSending(false);
  }, [item, onRegistered, tracking]);

  if (!tracking) {
    return (
      <div className="mt-3">
        <StatusBadge entry={null} trackable={false} />
        <p className="mt-1 text-xs text-muted">
          Plain tickers feed scans — they are not graded as individual picks.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-border/60 bg-surface-elevated p-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge entry={entry} trackable />
        {!entry && (
          <button
            type="button"
            onClick={() => void send()}
            disabled={sending}
            className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {sending ? "Sending…" : "Send to Performance"}
          </button>
        )}
        {entry?.outcome === "pending" && (
          <span className="text-[10px] text-muted">
            Auto-grades after the event/window settles — or log below.
          </span>
        )}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
      {entry && (
        <LogOutcomeButtons
          module={tracking.module}
          signalId={tracking.signalId}
          signalSnapshot={tracking.signalSnapshot}
          initialOutcome={{
            outcome: entry.outcome,
            resolution_source: entry.resolution_source,
            return_pct: entry.return_pct,
          }}
          compact
        />
      )}
    </div>
  );
}

export { statusKey as performanceEntryKey };
