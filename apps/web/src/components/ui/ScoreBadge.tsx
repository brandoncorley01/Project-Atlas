interface ScoreBadgeProps {
  label: string;
  value: number | null;
  variant?: "confidence" | "risk" | "opportunity";
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

export function ScoreBadge({ label, value, variant = "opportunity" }: ScoreBadgeProps) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-border-subtle bg-background/80 px-2.5 py-2 sm:px-3">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted sm:text-xs">
        {label}
      </span>
      <span className={`text-base font-bold tabular-nums sm:text-lg ${scoreColor(variant, value)}`}>
        {value !== null ? value.toFixed(0) : "—"}
      </span>
    </div>
  );
}
