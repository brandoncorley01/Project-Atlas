interface ScoreBadgeProps {
  label: string;
  value: number | null;
  variant?: "confidence" | "risk" | "opportunity";
  shortLabel?: string;
}

function scoreColor(variant: ScoreBadgeProps["variant"], value: number | null): string {
  if (value === null) return "text-muted";
  if (variant === "risk") {
    if (value >= 70) return "text-danger";
    if (value >= 40) return "text-warning";
    return "text-success";
  }
  if (value >= 75) return "text-success";
  if (value >= 50) return "text-warning";
  return "text-muted";
}

export function ScoreBadge({ label, shortLabel, value, variant = "opportunity" }: ScoreBadgeProps) {
  const mobileLabel = shortLabel ?? label;
  return (
    <div className="flex min-w-0 flex-col items-center rounded-lg border border-border-subtle bg-background/80 px-2 py-2 sm:px-3">
      <span className="text-center text-[10px] font-medium uppercase tracking-wide text-muted sm:text-xs">
        <span className="sm:hidden">{mobileLabel}</span>
        <span className="hidden sm:inline">{label}</span>
      </span>
      <span className={`text-base font-bold tabular-nums sm:text-lg ${scoreColor(variant, value)}`}>
        {value !== null ? value.toFixed(0) : "—"}
      </span>
    </div>
  );
}
