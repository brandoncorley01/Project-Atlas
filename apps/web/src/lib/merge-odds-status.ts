import type { OddsKeyProbeResult } from "@/lib/odds-key-probe";

type OddsLike = Record<string, unknown> | null | undefined;

/** Overlay live multi-key probe totals onto a providers/status odds_api payload. */
export function mergeOddsKeyProbe<T extends OddsLike>(odds: T, probe: OddsKeyProbeResult): NonNullable<T> {
  const base = { ...(odds ?? {}) } as NonNullable<T>;
  if (!probe.keys.length) return base;

  return {
    ...base,
    key_count: probe.key_count ?? base.key_count,
    keys: probe.keys,
    total_remaining: probe.total_remaining ?? base.total_remaining,
    monthly_capacity: probe.monthly_capacity ?? base.monthly_capacity,
    active_key_index: probe.active_key_index ?? base.active_key_index,
    connected: probe.connected ?? base.connected,
    requests_remaining: String(probe.total_remaining ?? base.requests_remaining ?? ""),
  };
}
