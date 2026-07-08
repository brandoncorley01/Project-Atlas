export function midpoint(low?: number, high?: number): number | null {
  if (low == null || high == null) return null;
  return (low + high) / 2;
}

export function riskRewardRatio(
  entry: number | null,
  stop: number | null,
  target: number | null,
): number | null {
  if (entry == null || stop == null || target == null) return null;
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  if (risk <= 0) return null;
  return reward / risk;
}

export function formatRiskReward(ratio: number | null): string {
  if (ratio == null || Number.isNaN(ratio)) return "—";
  return `${ratio.toFixed(1)}:1`;
}
