"use client";

import { useEffect, useState } from "react";
import { getPerformanceOutcome } from "@/lib/performance-api";

interface PickPerformanceBadgeProps {
  module: "options" | "stock" | "sports" | "parlay";
  signalId: string;
  className?: string;
}

/** Compact status chip for picks shown outside the watchlist. */
export function PickPerformanceBadge({
  module,
  signalId,
  className = "",
}: PickPerformanceBadgeProps) {
  const [label, setLabel] = useState<string | null>(null);
  const [tone, setTone] = useState("bg-sky-500/15 text-sky-300");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const entry = await getPerformanceOutcome(module, signalId);
        if (cancelled) return;
        if (!entry) {
          setLabel("Tracked on settle");
          setTone("bg-background text-muted");
          return;
        }
        if (entry.outcome === "pending") {
          setLabel("In Performance");
          setTone("bg-sky-500/15 text-sky-300");
          return;
        }
        const pct =
          entry.return_pct != null
            ? ` ${entry.return_pct > 0 ? "+" : ""}${entry.return_pct}%`
            : "";
        setLabel(`${entry.outcome}${pct}`);
        setTone(
          entry.outcome === "win"
            ? "bg-emerald-500/15 text-emerald-300"
            : entry.outcome === "loss"
              ? "bg-red-500/15 text-red-300"
              : "bg-background text-muted",
        );
      } catch {
        if (!cancelled) setLabel(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [module, signalId]);

  if (!label) return null;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${tone} ${className}`}
    >
      {label}
    </span>
  );
}
