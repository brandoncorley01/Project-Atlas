"use client";

import Link from "next/link";
import type { DashboardWarning } from "@/lib/dashboard-warnings";

const SEVERITY_STYLES: Record<DashboardWarning["severity"], string> = {
  error: "border-red-500/40 bg-red-500/10",
  warn: "border-amber-500/40 bg-amber-500/10",
  info: "border-border bg-surface/60",
};

const SEVERITY_LABEL: Record<DashboardWarning["severity"], string> = {
  error: "Error",
  warn: "Warning",
  info: "Notice",
};

interface DashboardLoadWarningsProps {
  warnings: DashboardWarning[];
  /** When true, also show soft info notices (timeouts that did not break the board). */
  includeInfo?: boolean;
  onRetry?: () => void;
}

export function DashboardLoadWarnings({
  warnings,
  includeInfo = false,
  onRetry,
}: DashboardLoadWarningsProps) {
  const visible = includeInfo
    ? warnings
    : warnings.filter((w) => w.severity === "warn" || w.severity === "error");

  if (visible.length === 0) return null;

  const errors = visible.filter((w) => w.severity === "error").length;
  const warns = visible.filter((w) => w.severity === "warn").length;
  const title =
    errors > 0
      ? `${errors} load error${errors === 1 ? "" : "s"}`
      : `${warns} warning${warns === 1 ? "" : "s"}`;

  return (
    <details className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 open:pb-1">
      <summary className="cursor-pointer list-none px-4 py-3 text-sm">
        <span className="font-medium text-amber-200">{title}</span>
        <span className="ml-2 text-muted">
          — tap for what failed and how to fix it
        </span>
      </summary>
      <ul className="space-y-2 px-4 pb-3">
        {visible.map((w) => (
          <li
            key={`${w.code}-${w.message}`}
            className={`rounded-lg border px-3 py-2.5 ${SEVERITY_STYLES[w.severity]}`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-medium text-foreground">
                <span className="mr-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                  {SEVERITY_LABEL[w.severity]}
                </span>
                {w.message}
              </p>
              {w.action && (
                <Link
                  href={w.action.href}
                  className="text-xs font-semibold text-accent hover:underline"
                >
                  {w.action.label} →
                </Link>
              )}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              <span className="font-medium text-foreground/80">How to fix: </span>
              {w.fix}
            </p>
            {w.detail && (
              <p className="mt-1 font-mono text-[10px] text-muted/80 break-all">
                {w.detail}
              </p>
            )}
          </li>
        ))}
      </ul>
      {onRetry && (
        <div className="border-t border-border/60 px-4 py-2">
          <button
            type="button"
            onClick={onRetry}
            className="text-xs font-semibold text-accent hover:underline"
          >
            Retry Home load
          </button>
        </div>
      )}
    </details>
  );
}
