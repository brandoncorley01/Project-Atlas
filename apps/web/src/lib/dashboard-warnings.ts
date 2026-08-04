/**
 * Normalize dashboard meta.warnings (structured objects or legacy strings).
 */

export type WarningSeverity = "info" | "warn" | "error";

export interface DashboardWarningAction {
  label: string;
  href: string;
}

export interface DashboardWarning {
  code: string;
  severity: WarningSeverity;
  message: string;
  fix: string;
  detail?: string;
  action?: DashboardWarningAction;
}

export interface WarningCounts {
  info: number;
  warn: number;
  error: number;
}

const LEGACY_HINTS: Record<string, { message: string; fix: string; href?: string; label?: string }> = {
  news_auto_refresh: {
    message: "Could not refresh headlines.",
    fix: "Open News and pull to refresh.",
    href: "/news",
    label: "Open News",
  },
  expire_stale: {
    message: "Cleanup of outdated plays was skipped.",
    fix: "Pull to refresh Home.",
    href: "/",
    label: "Retry Home",
  },
  signal_backfill: {
    message: "Performance tracking backfill was skipped.",
    fix: "Open Performance later.",
    href: "/performance",
    label: "Open Performance",
  },
  resolve_outcomes: {
    message: "Auto-grading was skipped.",
    fix: "Open Performance and use Sync if results look stale.",
    href: "/performance",
    label: "Open Performance",
  },
  market_intelligence: {
    message: "Market Intelligence summary was skipped.",
    fix: "Open Market Intel for the full view.",
    href: "/market-intelligence",
    label: "Open Market Intel",
  },
  atlas_briefing: {
    message: "AI briefing fell back to a template.",
    fix: "Tap Refresh on the briefing card, or check OpenAI under Data providers.",
    href: "/#data-providers",
    label: "Data providers",
  },
  top_opportunities: {
    message: "Options opportunities failed to load.",
    fix: "Retry Home, then run Options from the scanner.",
    href: "/options",
    label: "Open Options",
  },
  budget_opportunities: {
    message: "Budget options failed to load.",
    fix: "Retry Home, then run a deep Options scan.",
    href: "/options",
    label: "Open Options",
  },
  stock_opportunities: {
    message: "Stock swings failed to load.",
    fix: "Retry Home, then Scan stock swings.",
    href: "/stocks",
    label: "Open Stocks",
  },
  sports_opportunities: {
    message: "Sports plays failed to load.",
    fix: "Retry Home, then Scan sports odds.",
    href: "/sports",
    label: "Open Sports",
  },
};

function severityFromLegacy(code: string): WarningSeverity {
  if (
    code.includes("top_opportunities")
    || code.includes("budget_opportunities")
    || code.includes("stock_opportunities")
    || code.includes("sports_opportunities")
  ) {
    return "error";
  }
  if (
    code.includes("timed out")
    || code.startsWith("expire_stale")
    || code.startsWith("signal_backfill")
    || code.startsWith("resolve_outcomes")
    || code.startsWith("market_intelligence")
    || code.startsWith("atlas_briefing")
    || code.startsWith("news:")
    || code.includes("auto-refreshed")
  ) {
    return "info";
  }
  return "warn";
}

function parseLegacyString(raw: string): DashboardWarning {
  const trimmed = raw.trim();
  const code = trimmed.split(":")[0]?.trim() || "unknown";
  const hint = LEGACY_HINTS[code];
  const detail = trimmed.includes(":") ? trimmed.slice(trimmed.indexOf(":") + 1).trim() : undefined;
  return {
    code,
    severity: severityFromLegacy(code),
    message: hint?.message || trimmed,
    fix: hint?.fix || "Pull to refresh Home. If this keeps happening, check Data providers.",
    detail: hint ? detail : undefined,
    action: hint?.href
      ? { label: hint.label || "Open", href: hint.href }
      : { label: "Data providers", href: "/#data-providers" },
  };
}

export function normalizeDashboardWarnings(raw: unknown): DashboardWarning[] {
  if (!Array.isArray(raw)) return [];
  const out: DashboardWarning[] = [];
  for (const item of raw) {
    if (typeof item === "string") {
      // Ignore the old success-as-warning noise.
      if (item.includes("auto-refreshed stale headlines")) continue;
      out.push(parseLegacyString(item));
      continue;
    }
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const code = String(obj.code || "unknown");
      const severity = (["info", "warn", "error"].includes(String(obj.severity))
        ? String(obj.severity)
        : "warn") as WarningSeverity;
      const message = String(obj.message || code);
      const fix = String(
        obj.fix
          || "Pull to refresh Home. If this keeps happening, check Data providers.",
      );
      const action =
        obj.action && typeof obj.action === "object"
          ? {
              label: String((obj.action as Record<string, unknown>).label || "Fix"),
              href: String((obj.action as Record<string, unknown>).href || "/"),
            }
          : undefined;
      out.push({
        code,
        severity,
        message,
        fix,
        detail: obj.detail != null ? String(obj.detail) : undefined,
        action,
      });
    }
  }
  return out;
}

export function countActionableWarnings(warnings: DashboardWarning[]): WarningCounts {
  const counts: WarningCounts = { info: 0, warn: 0, error: 0 };
  for (const w of warnings) {
    counts[w.severity] += 1;
  }
  return counts;
}

/** Warnings that should surface as "partial load" (not soft info notices). */
export function actionableWarnings(warnings: DashboardWarning[]): DashboardWarning[] {
  return warnings.filter((w) => w.severity === "warn" || w.severity === "error");
}
