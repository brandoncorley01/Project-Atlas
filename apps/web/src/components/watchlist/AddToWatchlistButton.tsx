"use client";

import { useState } from "react";
import { addWatchlistItem } from "@/lib/watchlist-api";
import type { WatchlistItemType } from "@/lib/watchlist-types";

interface AddToWatchlistButtonProps {
  symbol: string;
  itemType: WatchlistItemType;
  metadata?: Record<string, unknown>;
  label?: string;
  savedLabel?: string;
  className?: string;
  variant?: "primary" | "ghost" | "compact";
  onAdded?: () => void;
}

export function AddToWatchlistButton({
  symbol,
  itemType,
  metadata,
  label = "Save to watchlist",
  savedLabel = "Saved ✓",
  className = "",
  variant = "ghost",
  onAdded,
}: AddToWatchlistButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    if (state === "saved" || state === "loading") return;
    setState("loading");
    setError(null);
    const result = await addWatchlistItem({ symbol, item_type: itemType, metadata });
    if (result.ok) {
      setState("saved");
      onAdded?.();
      setTimeout(() => setState("idle"), 2500);
    } else {
      setState("error");
      setError(result.error);
      setTimeout(() => setState("idle"), 3000);
    }
  }

  const base =
    variant === "primary"
      ? "rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
      : variant === "compact"
        ? "text-xs font-medium text-accent hover:underline disabled:opacity-50"
        : "rounded-lg border border-border bg-surface-elevated px-3 py-1.5 text-xs font-medium text-foreground hover:border-accent/50 disabled:opacity-50";

  const text =
    state === "loading" ? "Saving…" : state === "saved" ? savedLabel : state === "error" ? "Retry" : label;

  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button
        type="button"
        onClick={handleClick}
        disabled={state === "loading" || state === "saved"}
        className={`${base} ${className}`}
        title={error ?? undefined}
      >
        {state === "saved" ? "★ " : "☆ "}
        {text}
      </button>
      {error && state === "error" && <span className="text-[10px] text-danger">{error}</span>}
    </span>
  );
}
