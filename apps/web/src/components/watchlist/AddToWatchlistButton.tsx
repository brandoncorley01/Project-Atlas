"use client";

import { useEffect, useState } from "react";
import { addWatchlistItem } from "@/lib/watchlist-api";
import type { WatchlistItemType } from "@/lib/watchlist-types";
import { useWatchlistOptional } from "@/components/watchlist/WatchlistProvider";

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
  const watchlist = useWatchlistOptional();
  const alreadySaved = watchlist?.isSaved(symbol, itemType) ?? false;
  const [state, setState] = useState<"idle" | "loading" | "saved" | "error">(
    alreadySaved ? "saved" : "idle",
  );
  const [error, setError] = useState<string | null>(null);

  const isSaved = alreadySaved || state === "saved";

  useEffect(() => {
    if (alreadySaved) {
      setState("saved");
    }
  }, [alreadySaved]);

  async function handleClick() {
    if (isSaved || state === "loading") return;
    setState("loading");
    setError(null);
    const result = await addWatchlistItem({ symbol, item_type: itemType, metadata });
    if (result.ok) {
      watchlist?.markSaved(result.item);
      setState("saved");
      onAdded?.();
    } else {
      setState("error");
      setError(result.error);
      setTimeout(() => setState(alreadySaved ? "saved" : "idle"), 3000);
    }
  }

  const base =
    variant === "primary"
      ? "rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
      : variant === "compact"
        ? "text-xs font-medium text-accent hover:underline disabled:opacity-50"
        : "rounded-lg border border-border bg-surface-elevated px-3 py-1.5 text-xs font-medium text-foreground hover:border-accent/50 disabled:opacity-50";

  const text = isSaved
    ? savedLabel
    : state === "loading"
      ? "Saving…"
      : state === "error"
        ? "Retry"
        : label;

  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button
        type="button"
        onClick={handleClick}
        disabled={state === "loading" || isSaved}
        className={`${base} ${isSaved ? "border-accent/40 text-accent" : ""} ${className}`}
        title={error ?? undefined}
        aria-pressed={isSaved}
      >
        {isSaved ? "★ " : "☆ "}
        {text}
      </button>
      {error && state === "error" && <span className="text-[10px] text-danger">{error}</span>}
    </span>
  );
}
