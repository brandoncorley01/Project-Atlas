"use client";

import Link from "next/link";
import type { DashboardWarning } from "@/lib/dashboard-warnings";
import { humanStepName, type FixAllStep } from "@/lib/dashboard-fix";

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
  /** Show soft info notices too (e.g. after Fix all). */
  includeInfo?: boolean;
  fixing?: boolean;
  fixMessage?: string | null;
  fixSteps?: FixAllStep[];
  onFixAll?: () => void;
  onRetry?: () => void;
}

export function DashboardLoadWarnings({
  warnings,
  includeInfo = false,
  fixing = false,
  fixMessage = null,
  fixSteps = [],
  onFixAll,
  onRetry,
}: DashboardLoadWarningsProps) {
  const errors = warnings.filter((w) => w.severity === "error");
  const visible = includeInfo
    ? warnings
    : errors.length > 0
      ? errors
      : warnings.filter((w) => w.severity === "warn");
  const failedSteps = fixSteps.filter((s) => !s.ok);

  // Always show the strip when Fix all is available and there is something to show,
  // or when the parent forces visibility via errors.
  if (visible.length === 0 && !fixMessage && failedSteps.length === 0) return null;

  const title =
    errors.length > 0
      ? `${errors.length} load error${errors.length === 1 ? "" : "s"}`
      : failedSteps.length > 0
        ? `${failedSteps.length} Fix all step${failedSteps.length === 1 ? "" : "s"} need attention`
        : visible.length > 0
          ? `${visible.length} notice${visible.length === 1 ? "" : "s"}`
          : "Repair status";

  return (
    <details
      className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 open:pb-1"
      open={errors.length > 0 || Boolean(fixMessage) || failedSteps.length > 0}
    >
      <summary className="cursor-pointer list-none px-4 py-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="font-medium text-amber-200">{title}</span>
            <span className="ml-2 text-muted">— what failed and how to fix it</span>
          </div>
          {onFixAll && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onFixAll();
              }}
              disabled={fixing}
              className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-black hover:bg-amber-400 disabled:opacity-60"
            >
              {fixing ? "Fixing…" : "Fix all"}
            </button>
          )}
        </div>
      </summary>

      {fixMessage && (
        <p className="mx-4 mb-2 rounded-md border border-border/70 bg-background/40 px-3 py-2 text-xs text-muted">
          {fixMessage}
        </p>
      )}

      {failedSteps.length > 0 && (
        <ul className="space-y-2 px-4 pb-3">
          {failedSteps.map((s) => (
            <li
              key={s.step}
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2.5"
            >
              <p className="text-sm font-medium text-foreground">
                <span className="mr-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                  Failed
                </span>
                {humanStepName(s.step)}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                {String(s.error || s.message || "Step failed")}
              </p>
              {s.step === "refresh_sports" && (
                <p className="mt-1 text-xs text-muted">
                  <span className="font-medium text-foreground/80">How to fix: </span>
                  Open Sports → Fetch live odds once to seed FanDuel/DraftKings lines, then Scan.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {visible.length > 0 && (
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
                <p className="mt-1 break-all font-mono text-[10px] text-muted/80">
                  {w.detail}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-3 border-t border-border/60 px-4 py-2">
        {onFixAll && (
          <button
            type="button"
            onClick={onFixAll}
            disabled={fixing}
            className="text-xs font-semibold text-accent hover:underline disabled:opacity-60"
          >
            {fixing ? "Running Fix all…" : "Run Fix all again"}
          </button>
        )}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={fixing}
            className="text-xs font-semibold text-muted hover:text-foreground hover:underline disabled:opacity-60"
          >
            Retry Home load
          </button>
        )}
        <Link
          href="/sports"
          className="text-xs font-semibold text-muted hover:text-accent hover:underline"
        >
          Open Sports →
        </Link>
      </div>
    </details>
  );
}
