"use client";

import Link from "next/link";

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
  takeaway?: string;
};

function tone(value: number) {
  if (value > 0.5) return "bg-emerald-500/30 border-emerald-400/40 text-emerald-50";
  if (value < -0.5) return "bg-rose-500/30 border-rose-400/40 text-rose-50";
  return "bg-slate-500/20 border-slate-400/30 text-slate-100";
}

function biasWords(tile: Tile): string {
  if (tile.exit_urgency != null) {
    const u = Number(tile.exit_urgency);
    if (u >= 71) return "Review exit soon";
    if (u >= 56) return "Tighten risk";
    if (u >= 41) return "Monitor closely";
    return "Hold posture OK";
  }
  const bias = Number(tile.options_bias ?? tile.color_value ?? tile.daily_return ?? 0);
  if (bias > 0.5) return "Bullish lean";
  if (bias < -0.5) return "Bearish / defensive lean";
  return "No clear lean";
}

export function HeatmapPanel({
  title,
  subtitle,
  meaning,
  sectors,
  tableFallback,
  legend,
  linkModule = "options-intelligence",
}: {
  title: string;
  subtitle?: string;
  meaning?: string;
  sectors?: Array<{ sector: string; tiles: Tile[] }>;
  tableFallback?: Tile[];
  legend?: { size?: string; color?: string; note?: string };
  linkModule?: "options-intelligence" | "stocks";
}) {
  const flat = tableFallback?.length
    ? tableFallback
    : (sectors ?? []).flatMap((s) => s.tiles);

  const constructive = flat.filter((t) => Number(t.options_bias ?? t.color_value ?? 0) > 0.4);
  const pressured = flat.filter((t) => Number(t.options_bias ?? t.color_value ?? 0) < -0.4);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        {meaning && (
          <p className="mt-2 rounded-lg border border-border/70 bg-surface/50 px-3 py-2 text-sm text-foreground/90">
            {meaning}
          </p>
        )}
        {legend && (
          <p className="mt-2 text-xs text-muted">
            Tile size reflects {legend.size}. Color lean reflects {legend.color}. {legend.note}
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <SummaryBox
          title="Constructive focus"
          empty="No clear constructive names right now."
          items={constructive.map((t) => `${t.symbol}: ${t.takeaway || t.label || biasWords(t)}`)}
        />
        <SummaryBox
          title="Pressured / caution"
          empty="No clear pressured names right now."
          items={pressured.map((t) => `${t.symbol}: ${t.takeaway || t.label || biasWords(t)}`)}
        />
      </div>

      <div className="hidden md:block">
        {(sectors ?? []).map((sector) => (
          <div key={sector.sector} className="mb-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {sector.sector}
            </p>
            <div className="flex flex-wrap gap-2">
              {sector.tiles.map((tile) => {
                const size = Math.max(88, Math.min(150, Math.sqrt(Number(tile.size_value || 1)) / 60 + 88));
                const colorVal = Number(tile.color_value ?? tile.daily_return ?? tile.options_bias ?? 0);
                return (
                  <Link
                    key={`${sector.sector}-${tile.symbol}`}
                    href={
                      linkModule === "stocks"
                        ? `/stocks?ticker=${encodeURIComponent(String(tile.symbol ?? ""))}`
                        : `/options-intelligence`
                    }
                    className={`flex flex-col justify-between rounded-lg border p-2.5 transition-opacity hover:opacity-90 ${tone(colorVal)}`}
                    style={{ width: size, minHeight: size * 0.75 }}
                    title={tile.takeaway || tile.why || tile.label}
                  >
                    <span className="text-sm font-bold">{tile.symbol}</span>
                    <span className="text-[11px] leading-snug opacity-95">
                      {tile.label || biasWords(tile)}
                    </span>
                    {tile.exit_urgency != null && (
                      <span className="text-[10px]">Urgency {Number(tile.exit_urgency).toFixed(0)}</span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
          <thead className="bg-background/50 text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Sector</th>
              <th className="px-3 py-2">Read</th>
              <th className="px-3 py-2">What to do with it</th>
            </tr>
          </thead>
          <tbody>
            {flat.map((tile) => (
              <tr key={`${tile.sector}-${tile.symbol}`} className="border-t border-border/60 align-top">
                <td className="px-3 py-2.5 font-medium">{tile.symbol}</td>
                <td className="px-3 py-2.5 text-muted">{tile.sector}</td>
                <td className="px-3 py-2.5">{tile.label || biasWords(tile)}</td>
                <td className="px-3 py-2.5 text-muted">
                  {tile.takeaway || tile.action || tile.why || "Use as confirmation only — not a standalone order."}
                </td>
              </tr>
            ))}
            {flat.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-muted">
                  No names in focus yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryBox({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface/50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
      <ul className="mt-2 space-y-1.5 text-sm">
        {items.length === 0 && <li className="text-muted">{empty}</li>}
        {items.slice(0, 4).map((item) => (
          <li key={item} className="text-foreground/90">
            • {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
