"use client";

import { SignalsActions } from "@/components/dashboard/SignalsActions";

export function MarketScanBar() {
  return (
    <section className="atlas-card mb-6 overflow-hidden border-border/80 bg-surface-elevated/80 p-4 sm:p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0 shrink-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-accent">Scanner</p>
          <h2 className="mt-0.5 text-base font-semibold text-foreground sm:text-lg">Run market scans</h2>
          <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">
            Ranked options, stock swings, sports odds, and parlays — one bar, no duplicate clicks across pages.
          </p>
        </div>
        <SignalsActions />
      </div>
    </section>
  );
}
