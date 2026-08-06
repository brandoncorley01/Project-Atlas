/** Format an options strike so 18.0 and 18.5 never both render as "$18". */
export function formatStrike(strike: number | string | null | undefined): string {
  const n = Number(strike ?? 0);
  if (!Number.isFinite(n)) return "0";
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n));
  return n.toFixed(1).replace(/\.0$/, "");
}
