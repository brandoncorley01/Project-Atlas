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

function tone(value: number) {
  if (value > 0.5) return "bg-emerald-500/35 border-emerald-400/40 text-emerald-50";
  if (value < -0.5) return "bg-rose-500/35 border-rose-400/40 text-rose-50";
  return "bg-slate-500/25 border-slate-400/30 text-slate-100";
}

export function HeatmapPanel({
  title,
  subtitle,
  sectors,
  tableFallback,
  legend,
}: {
  title: string;
  subtitle?: string;
  sectors?: Array<{ sector: string; tiles: Tile[] }>;
  tableFallback?: Tile[];
  legend?: { size?: string; color?: string; note?: string };
}) {
  const flat = tableFallback?.length
    ? tableFallback
    : (sectors ?? []).flatMap((s) => s.tiles);

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

      <div className="hidden gap-3 md:block">
        {(sectors ?? []).map((sector) => (
          <div key={sector.sector} className="mb-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {sector.sector}
            </p>
            <div className="flex flex-wrap gap-2">
              {sector.tiles.map((tile) => {
                const size = Math.max(72, Math.min(160, Math.sqrt(Number(tile.size_value || 1)) / 50 + 72));
                const colorVal = Number(tile.color_value ?? tile.daily_return ?? tile.options_bias ?? 0);
                return (
                  <div
                    key={`${sector.sector}-${tile.symbol}`}
                    className={`flex flex-col justify-between rounded-lg border p-2 ${tone(colorVal)}`}
                    style={{ width: size, minHeight: size * 0.7 }}
                    title={tile.why || tile.label}
                  >
                    <span className="text-sm font-bold">{tile.symbol}</span>
                    <span className="text-[10px] opacity-90">{tile.label || "—"}</span>
                    {tile.exit_urgency != null && (
                      <span className="text-[10px]">Exit {Number(tile.exit_urgency).toFixed(0)}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Accessible table fallback (also primary on mobile) */}
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
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
            {flat.map((tile) => (
              <tr key={`${tile.sector}-${tile.symbol}`} className="border-t border-border/60">
                <td className="px-3 py-2 font-medium">{tile.symbol}</td>
                <td className="px-3 py-2 text-muted">{tile.sector}</td>
                <td className="px-3 py-2">{tile.label || "—"}</td>
                <td className="px-3 py-2">
                  {tile.exit_urgency != null
                    ? `Exit ${Number(tile.exit_urgency).toFixed(0)}`
                    : tile.options_bias != null
                      ? `Bias ${Number(tile.options_bias).toFixed(2)}`
                      : tile.daily_return != null
                        ? `${Number(tile.daily_return).toFixed(2)}`
                        : "—"}
                </td>
                <td className="px-3 py-2 text-muted">{tile.action || "—"}</td>
              </tr>
            ))}
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
