"use client";

import Link from "next/link";

interface FreshnessMeta {
  needs_refresh?: {
    sports?: boolean;
    stocks?: boolean;
    options?: boolean;
    news?: boolean;
  };
  expired_purged?: Record<string, number>;
}

const MODULE_FIX: Record<string, { href: string; label: string; how: string }> = {
  sports: {
    href: "/sports",
    label: "Sports",
    how: "Open Sports → Scan sports odds",
  },
  stocks: {
    href: "/stocks",
    label: "Stocks",
    how: "Open Stocks → Scan stock swings",
  },
  options: {
    href: "/options",
    label: "Options",
    how: "Open Options → run a deep scan",
  },
  news: {
    href: "/news",
    label: "News",
    how: "Open News and pull to refresh",
  },
};

export function StaleDataBanner({ meta }: { meta?: FreshnessMeta }) {
  const needs = meta?.needs_refresh;
  const purged = meta?.expired_purged;
  const totalPurged = purged
    ? Object.values(purged).reduce((sum, n) => sum + (n || 0), 0)
    : 0;

  const staleModules: string[] = [];
  if (needs?.sports) staleModules.push("sports");
  if (needs?.stocks) staleModules.push("stocks");
  if (needs?.options) staleModules.push("options");
  if (needs?.news) staleModules.push("news");

  if (!totalPurged && staleModules.length === 0) return null;

  return (
    <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
      <p className="font-medium text-amber-200">Outdated signals hidden</p>
      <p className="mt-1 text-muted">
        {totalPurged > 0 && (
          <>
            Removed {totalPurged} expired play{totalPurged === 1 ? "" : "s"} (past events or old scans).
            {" "}
          </>
        )}
        {staleModules.length > 0 ? (
          <>No current {staleModules.join(", ")} data — run a fresh scan for today&apos;s board.</>
        ) : (
          <>Showing only actionable, up-to-date plays.</>
        )}
      </p>
      {staleModules.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {staleModules.map((mod) => {
            const fix = MODULE_FIX[mod];
            if (!fix) return null;
            return (
              <li key={mod} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="text-muted">
                  <span className="font-medium text-foreground/85">How to fix: </span>
                  {fix.how}
                </span>
                <Link href={fix.href} className="font-semibold text-accent hover:underline">
                  {fix.label} →
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
