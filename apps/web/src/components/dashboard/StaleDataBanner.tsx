"use client";

interface FreshnessMeta {
  needs_refresh?: {
    sports?: boolean;
    stocks?: boolean;
    options?: boolean;
    news?: boolean;
  };
  expired_purged?: Record<string, number>;
}

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
          <>
            No current {staleModules.join(", ")} data — run a fresh scan to see today&apos;s
            opportunities.
          </>
        ) : (
          <>Showing only actionable, up-to-date plays.</>
        )}
      </p>
    </div>
  );
}
