"use client";

type Tile = {
  symbol?: string;
  sector?: string;
  size_value?: number;
  color_value?: number;
  label?: string;
  daily_return?: number;
  exit_urgency?: number;
  options_bias?: number;
  action?: string;
  why?: string;
};

function tone(value: number, kind: "return" | "bias" | "urgency") {
  if (kind === "urgency") {
    if (value >= 71) return "bg-rose-500/45 border-rose-400/50 text-rose-50";
    if (value >= 41) return "bg-amber-500/35 border-amber-400/40 text-amber-50";
    return "bg-emerald-500/25 border-emerald-400/30 text-emerald-50";
  }
  // Equity % return or options bias (scaled)
  if (value >= 2) return "bg-emerald-600/55 border-emerald-400/50 text-emerald-50";
  if (value >= 0.5) return "bg-emerald-500/35 border-emerald-400/40 text-emerald-50";
  if (value <= -2) return "bg-rose-600/55 border-rose-400/50 text-rose-50";
  if (value <= -0.5) return "bg-rose-500/35 border-rose-400/40 text-rose-50";
  return "bg-slate-500/25 border-slate-400/30 text-slate-100";
}

function metricKind(colorBy?: string, tiles: Tile[] = []): "return" | "bias" | "urgency" {
  if (colorBy === "exit_urgency" || tiles.some((t) => t.exit_urgency != null)) {
    return "urgency";
  }
  if (colorBy === "options_bias") return "bias";
  return "return";
}

function formatMetric(tile: Tile, colorBy?: string) {
  const kind = metricKind(colorBy, [tile]);
  if (kind === "urgency") {
    return `Exit ${Number(tile.exit_urgency ?? tile.color_value ?? 0).toFixed(0)}`;
  }
  if (kind === "bias") {
    const v = Number(tile.options_bias ?? tile.color_value ?? 0);
    return `Bias ${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
  }
  const ret = Number(tile.daily_return ?? tile.color_value ?? 0);
  return `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`;
}

function colorValue(tile: Tile, kind: "return" | "bias" | "urgency") {
  if (kind === "urgency") {
    return Number(tile.exit_urgency ?? tile.color_value ?? 0);
  }
  if (kind === "bias") {
    return Number(tile.options_bias ?? tile.color_value ?? 0);
  }
  return Number(tile.daily_return ?? tile.color_value ?? 0);
}

export function HeatmapPanel({
  title,
  subtitle,
  sectors,
  tableFallback,
  legend,
  colorBy,
}: {
  title: string;
  subtitle?: string;
  sectors?: Array<{ sector: string; tiles: Tile[] }>;
  tableFallback?: Tile[];
  legend?: { size?: string; color?: string; note?: string };
  colorBy?: string;
}) {
  const flat = tableFallback?.length
    ? tableFallback
    : (sectors ?? []).flatMap((s) => s.tiles);

  const kind = metricKind(colorBy, flat);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
        {legend && (
          <p className="mt-1 text-xs text-muted">
            Size: {legend.size} · Color: {legend.color}. {legend.note}
          </p>
        )}
      </div>

      <div className="space-y-3">
        {(sectors ?? []).map((sector) => (
          <div key={sector.sector}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {sector.sector}
            </p>
            <div className="flex flex-wrap gap-2">
              {sector.tiles.map((tile) => {
                const size = Math.max(
                  64,
                  Math.min(168, Math.sqrt(Number(tile.size_value || 1)) / 80_000 + 64),
                );
                const colorVal = colorValue(tile, kind);
                return (
                  <div
                    key={`${sector.sector}-${tile.symbol}`}
                    className={`flex flex-col justify-between rounded-lg border p-2 ${tone(colorVal, kind)}`}
                    style={{ width: size, minHeight: size * 0.72 }}
                    title={tile.why || tile.label}
                  >
                    <span className="text-sm font-bold">{tile.symbol}</span>
                    <span className="text-[11px] font-semibold opacity-95">
                      {formatMetric(tile, colorBy)}
                    </span>
                    <span className="text-[10px] opacity-90">{tile.label || "—"}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <thead className="bg-background/50 text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Sector</th>
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2">Metric</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {flat.map((tile) => {
              const colorVal = colorValue(tile, kind);
              return (
                <tr key={`${tile.sector}-${tile.symbol}`} className="border-t border-border/60">
                  <td className="px-3 py-2 font-medium">{tile.symbol}</td>
                  <td className="px-3 py-2 text-muted">{tile.sector}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block rounded border px-1.5 py-0.5 text-[11px] ${tone(colorVal, kind)}`}
                    >
                      {tile.label || "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2">{formatMetric(tile, colorBy)}</td>
                  <td className="px-3 py-2 text-muted">{tile.action || tile.why || "—"}</td>
                </tr>
              );
            })}
            {flat.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-muted">
                  No heatmap tiles yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
