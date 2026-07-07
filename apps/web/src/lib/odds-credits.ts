export interface OddsKeyCredits {
  remaining?: number | null;
}

export interface OddsCreditsSource {
  total_remaining?: number | null;
  keys?: OddsKeyCredits[];
  requests_remaining?: string | number | null;
  key_count?: number;
}

/** Prefer summed credits across all failover keys when breakdown is available. */
export function resolveOddsTotalCredits(odds: OddsCreditsSource | null | undefined): number | null {
  if (!odds) return null;

  const keys = odds.keys ?? [];
  if (keys.length > 0) {
    const sum = keys.reduce((acc, k) => acc + Math.max(0, k.remaining ?? 0), 0);
    return sum;
  }

  if (odds.total_remaining != null && odds.total_remaining > 0) {
    return odds.total_remaining;
  }

  const raw = odds.requests_remaining;
  if (raw != null && raw !== "") {
    const parsed = typeof raw === "number" ? raw : parseInt(String(raw), 10);
    if (!Number.isNaN(parsed)) return parsed;
  }

  return odds.total_remaining ?? null;
}
