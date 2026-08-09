"use client";

export interface KalshiPublicSide {
  abbr: string;
  label: string;
  implied_pct: number;
  market_ticker?: string | null;
}

export interface KalshiPublicMarket {
  source?: string;
  series_ticker?: string;
  event_ticker?: string;
  title?: string;
  as_of?: string;
  url?: string | null;
  side_a: KalshiPublicSide;
  side_b: KalshiPublicSide;
  history_a?: number[];
  history_b?: number[];
  stance_vs_pick?: "sure" | "mixed" | "doubtful" | string | null;
}

function stanceCopy(stance?: string | null) {
  if (stance === "sure") return "Public sure on your side";
  if (stance === "doubtful") return "Public leans against";
  if (stance === "mixed") return "Public mixed";
  return "Public market";
}

function stanceClass(stance?: string | null) {
  if (stance === "sure") return "text-teal-300";
  if (stance === "doubtful") return "text-rose-300";
  return "text-zinc-400";
}

/** Build a smooth dual-line path: side A in the top half, side B mirrored below. */
function buildPaths(
  historyA: number[],
  historyB: number[],
  width: number,
  height: number,
): { top: string; bottom: string } {
  const n = Math.max(historyA.length, historyB.length, 1);
  const a = historyA.length ? historyA : [50];
  const b = historyB.length ? historyB : a.map((p) => 100 - p);
  const padX = 2;
  const mid = height / 2;
  const amp = height * 0.4;

  const point = (series: number[], i: number, side: "top" | "bottom") => {
    const idx = Math.min(i, series.length - 1);
    const pct = Math.max(0, Math.min(100, series[idx] ?? 50));
    const mag = (pct / 100) * amp;
    const y = side === "top" ? mid - mag : mid + mag;
    const x = padX + (i / Math.max(n - 1, 1)) * (width - padX * 2);
    return { x, y };
  };

  const toPath = (series: number[], side: "top" | "bottom") => {
    const pts = Array.from({ length: n }, (_, i) => point(series, i, side));
    if (pts.length === 1) {
      return `M ${padX} ${pts[0].y} L ${width - padX} ${pts[0].y}`;
    }
    let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < pts.length; i += 1) {
      const prev = pts[i - 1];
      const cur = pts[i];
      const cpx = (prev.x + cur.x) / 2;
      d += ` Q ${cpx.toFixed(1)} ${prev.y.toFixed(1)} ${cur.x.toFixed(1)} ${cur.y.toFixed(1)}`;
    }
    return d;
  };

  return { top: toPath(a, "top"), bottom: toPath(b, "bottom") };
}

export function KalshiPublicPulse({
  market,
  compact = false,
}: {
  market: KalshiPublicMarket;
  compact?: boolean;
}) {
  const sideA = market.side_a;
  const sideB = market.side_b;
  if (!sideA || !sideB) return null;

  const width = compact ? 168 : 200;
  const height = compact ? 44 : 52;
  const historyA = market.history_a?.length ? market.history_a : [sideA.implied_pct];
  const historyB = market.history_b?.length ? market.history_b : [sideB.implied_pct];
  const hasMotion = historyA.length >= 3 || historyB.length >= 3;
  const { top, bottom } = buildPaths(historyA, historyB, width, height);
  const title = stanceCopy(market.stance_vs_pick);
  const pctA = Math.round(Number(sideA.implied_pct));
  const pctB = Math.round(Number(sideB.implied_pct));

  const body = (
    <div
      className="flex min-w-0 flex-col gap-2"
      title={`${sideA.label} ${pctA}% · ${sideB.label} ${pctB}% — Kalshi public market`}
    >
      <div className="flex min-w-0 items-center gap-3">
        <div className="shrink-0">
          <p className="text-[11px] font-semibold tracking-wide text-zinc-300">Kalshi</p>
          <p className={`mt-0.5 text-[10px] leading-tight ${stanceClass(market.stance_vs_pick)}`}>
            {title}
          </p>
        </div>

        <div className="relative min-w-0 flex-1">
          {hasMotion ? (
            <svg
              viewBox={`0 0 ${width} ${height}`}
              width="100%"
              height={height}
              className="max-w-[220px] overflow-visible"
              aria-hidden
            >
              <line
                x1="0"
                y1={height / 2}
                x2={width}
                y2={height / 2}
                stroke="currentColor"
                className="text-zinc-600/70"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <path
                d={top}
                fill="none"
                stroke="#2dd4bf"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d={bottom}
                fill="none"
                stroke="#5eead4"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.85"
              />
            </svg>
          ) : (
            <div className="flex h-10 items-center gap-2">
              <div className="relative h-2.5 w-full max-w-[220px] overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-teal-400/90"
                  style={{ width: `${Math.max(4, Math.min(96, pctA))}%` }}
                />
                <div
                  className="absolute inset-y-0 right-0 rounded-full bg-teal-200/50"
                  style={{ width: `${Math.max(4, Math.min(96, pctB))}%` }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="shrink-0 text-right tabular-nums leading-tight">
          <p className="text-xs font-semibold text-teal-300">
            {sideA.abbr} {pctA}%
          </p>
          <p className="mt-1 text-xs font-semibold text-teal-100/90">
            {sideB.abbr} {pctB}%
          </p>
        </div>
      </div>
    </div>
  );

  if (market.url) {
    return (
      <a
        href={market.url}
        target="_blank"
        rel="noreferrer"
        className="mt-3 block rounded-xl border border-teal-400/30 bg-teal-500/10 px-3 py-2.5 transition hover:border-teal-300/50 hover:bg-teal-500/15"
      >
        {body}
      </a>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-teal-400/30 bg-teal-500/10 px-3 py-2.5">
      {body}
    </div>
  );
}
