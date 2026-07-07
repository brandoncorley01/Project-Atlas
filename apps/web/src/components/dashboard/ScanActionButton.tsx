"use client";

import type { ReactNode } from "react";

type ScanVariant = "primary" | "default" | "ghost";

interface ScanActionButtonProps {
  label: string;
  loadingLabel: string;
  loading?: boolean;
  disabled?: boolean;
  variant?: ScanVariant;
  onClick: () => void;
  title?: string;
}

const variantClass: Record<ScanVariant, string> = {
  primary:
    "bg-accent text-white shadow-sm shadow-accent/20 hover:bg-accent/90 data-[active=true]:ring-2 data-[active=true]:ring-accent/40",
  default:
    "text-foreground hover:bg-surface-hover data-[active=true]:bg-surface-hover data-[active=true]:ring-1 data-[active=true]:ring-border",
  ghost:
    "text-muted hover:bg-surface-hover hover:text-foreground data-[active=true]:bg-surface-hover",
};

export function ScanActionButton({
  label,
  loadingLabel,
  loading = false,
  disabled = false,
  variant = "default",
  onClick,
  title,
}: ScanActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      data-active={loading || undefined}
      className={`rounded-lg px-3 py-2 text-xs font-semibold tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-45 sm:px-3.5 sm:text-sm ${variantClass[variant]}`}
    >
      {loading ? loadingLabel : label}
    </button>
  );
}

export function ScanToolbarGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="px-1 text-[10px] font-semibold uppercase tracking-wider text-muted/80">
        {label}
      </span>
      <div className="flex rounded-xl border border-border bg-background/60 p-1 shadow-inner shadow-black/10">
        {children}
      </div>
    </div>
  );
}
