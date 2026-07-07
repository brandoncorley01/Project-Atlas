"use client";

const ZONES = [
  { label: "WORSE", color: "#dc2626" },
  { label: "BAD", color: "#f97316" },
  { label: "NORMAL", color: "#eab308" },
  { label: "GOOD", color: "#84cc16" },
  { label: "BEST", color: "#16a34a" },
] as const;

function zoneFromValue(value: number) {
  const clamped = Math.max(0, Math.min(100, value));
  if (clamped >= 80) return ZONES[4];
  if (clamped >= 60) return ZONES[3];
  if (clamped >= 40) return ZONES[2];
  if (clamped >= 20) return ZONES[1];
  return ZONES[0];
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polar(cx, cy, r, startDeg);
  const end = polar(cx, cy, r, endDeg);
  const large = Math.abs(startDeg - endDeg) > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y}`;
}

interface StatusGaugeProps {
  value: number;
  title: string;
  subtitle?: string;
  detail?: string;
  centerLabel?: string;
  size?: "sm" | "md";
}

export function StatusGauge({ value, title, subtitle, detail, centerLabel, size = "md" }: StatusGaugeProps) {
  const zone = zoneFromValue(value);
  const w = size === "sm" ? 200 : 240;
  const h = size === "sm" ? 120 : 140;
  const cx = w / 2;
  const cy = h - 8;
  const r = size === "sm" ? 72 : 88;
  const needleAngle = 180 - (Math.max(0, Math.min(100, value)) / 100) * 180;
  const needleTip = polar(cx, cy, r - 18, needleAngle);

  return (
    <div className="flex flex-col items-center text-center">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        {ZONES.map((z, i) => {
          const startDeg = 180 - i * 36;
          const endDeg = 180 - (i + 1) * 36;
          return (
            <path
              key={z.label}
              d={arcPath(cx, cy, r, startDeg, endDeg)}
              fill="none"
              stroke={z.color}
              strokeWidth={size === "sm" ? 14 : 18}
              strokeLinecap="butt"
            />
          );
        })}
        {/* Inner track */}
        <path
          d={arcPath(cx, cy, r - 22, 180, 0)}
          fill="none"
          stroke="var(--border)"
          strokeWidth={1}
        />
        {/* Tick marks */}
        {ZONES.map((_, i) => {
          const deg = 180 - i * 36;
          const inner = polar(cx, cy, r - 26, deg);
          const outer = polar(cx, cy, r - 18, deg);
          return (
            <line
              key={`tick-${i}`}
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              stroke="var(--foreground)"
              strokeWidth={2}
              opacity={0.35}
            />
          );
        })}
        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleTip.x}
          y2={needleTip.y}
          stroke="var(--foreground)"
          strokeWidth={3}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={6} fill="var(--foreground)" />
        {centerLabel && (
          <text
            x={cx}
            y={cy - 28}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="var(--foreground)"
            fontSize={size === "sm" ? 11 : 13}
            fontWeight={700}
          >
            {centerLabel}
          </text>
        )}
        {/* Zone labels */}
        {ZONES.map((z, i) => {
          const midDeg = 180 - i * 36 - 18;
          const pos = polar(cx, cy, r - 38, midDeg);
          return (
            <text
              key={`lbl-${z.label}`}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="var(--muted)"
              fontSize={size === "sm" ? 7 : 8}
              fontWeight={600}
            >
              {z.label}
            </text>
          );
        })}
      </svg>

      <p
        className="-mt-1 text-sm font-bold tracking-wide"
        style={{ color: zone.color }}
      >
        {zone.label}
      </p>
      <p className="mt-1 text-sm font-semibold text-foreground">{title}</p>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      {detail && (
        <p className="mt-2 max-w-xs text-xs leading-relaxed text-muted">{detail}</p>
      )}
    </div>
  );
}

export function finnhubGaugeValue(connected: boolean, configured: boolean, error?: string | null): number {
  if (error && !connected) return 12;
  if (connected) return 92;
  if (configured) return 52;
  return 28;
}

/** Map combined sports API credits to 0–100 for the gauge (scales with key count). */
export function oddsCreditsGaugeValue(
  remaining: number | null | undefined,
  configured: boolean,
  connected: boolean,
  quotaExhausted: boolean,
  keyCount = 1,
): number {
  if (!configured) return 8;
  if (quotaExhausted && (remaining ?? 0) <= 0) return 10;
  if (!connected && remaining == null) return 30;
  if (remaining == null) return 55;

  const capacity = Math.max(1, keyCount) * 500;
  const pct = (remaining / capacity) * 100;
  if (pct >= 70) return 92;
  if (pct >= 50) return 75;
  if (pct >= 30) return 58;
  if (pct >= 15) return 38;
  if (pct >= 5) return 22;
  return 12;
}
