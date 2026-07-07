type StatusVariant = "success" | "warning" | "danger" | "muted" | "loading";

const variantStyles: Record<StatusVariant, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-muted",
  loading: "bg-accent animate-pulse",
};

interface StatusPillProps {
  label: string;
  variant?: StatusVariant;
}

export function StatusPill({ label, variant = "muted" }: StatusPillProps) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted">
      <span className={`h-2 w-2 shrink-0 rounded-full ${variantStyles[variant]}`} aria-hidden />
      <span className={variant === "danger" ? "text-danger" : variant === "success" ? "text-success" : ""}>
        {label}
      </span>
    </span>
  );
}
