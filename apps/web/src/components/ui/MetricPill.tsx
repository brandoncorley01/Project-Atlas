import type { ReactNode } from "react";

interface MetricPillProps {
  children: ReactNode;
  variant?: "default" | "fanduel" | "success" | "muted";
  className?: string;
}

const variants = {
  default: "border-border bg-background text-foreground",
  fanduel: "border-fanduel/40 bg-fanduel-muted text-fanduel-text",
  success: "border-success/30 bg-success/10 text-success",
  muted: "border-border bg-background/50 text-muted",
};

export function MetricPill({ children, variant = "default", className = "" }: MetricPillProps) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
