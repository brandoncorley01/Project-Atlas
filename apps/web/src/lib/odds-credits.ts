export interface OddsKeyCredits {
  remaining?: number | null;
}

export interface OddsCreditsSource {
  total_remaining?: number | null;
  keys?: OddsKeyCredits[];
  requests_remaining?: string | number | null;
  key_count?: number;
}

/** Prefer API-summed total, then per-key breakdown, then legacy header. */
export function resolveOddsTotalCredits(odds: OddsCreditsSource | null | undefined): number | null {
  if (!odds) return null;

  if (odds.total_remaining != null && odds.total_remaining >= 0) {
    return odds.total_remaining;
  }

  const keys = odds.keys ?? [];
  if (keys.length > 0) {
    return keys.reduce((acc, k) => acc + Math.max(0, k.remaining ?? 0), 0);
  }

  const raw = odds.requests_remaining;
  if (raw != null && raw !== "") {
    const parsed = typeof raw === "number" ? raw : parseInt(String(raw), 10);
    if (!Number.isNaN(parsed)) return parsed;
  }

  return null;
}
