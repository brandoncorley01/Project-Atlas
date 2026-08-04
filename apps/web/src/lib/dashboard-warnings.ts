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
  repair?: string;
}

export interface WarningCounts {
  info: number;
  warn: number;
  error: number;
}

const LEGACY_HINTS: Record<string, { message: string; fix: string; href?: string; label?: string }> = {
  news_auto_refresh: {
    message: "Could not refresh headlines.",
    fix: "Tap Fix all to refresh news.",
    href: "/news",
    label: "Open News",
  },
  news_auto_refresh_timeout: {
    message: "News refresh timed out.",
    fix: "Tap Fix all to refresh news.",
    href: "/news",
    label: "Open News",
  },
  expire_stale: {
    message: "Cleanup of outdated plays was skipped.",
    fix: "Tap Fix all to clean outdated plays.",
    href: "/",
    label: "Retry Home",
  },
  signal_backfill: {
    message: "Performance tracking backfill was skipped.",
    fix: "Tap Fix all to backfill tracking.",
    href: "/performance",
    label: "Open Performance",
  },
  resolve_outcomes: {
    message: "Auto-grading was skipped.",
    fix: "Tap Fix all to grade finished picks.",
    href: "/performance",
    label: "Open Performance",
  },
  market_intelligence: {
    message: "Market Intelligence summary was skipped.",
    fix: "Open Market Intel, or tap Fix all.",
    href: "/market-intelligence",
    label: "Open Market Intel",
  },
  atlas_briefing: {
    message: "AI briefing fell back to a template.",
    fix: "Tap Fix all, then Refresh on the briefing card.",
    href: "/#data-providers",
    label: "Data providers",
  },
  top_opportunities: {
    message: "Options opportunities failed to load.",
    fix: "Tap Fix all to rescan options.",
    href: "/options",
    label: "Open Options",
  },
  budget_opportunities: {
    message: "Budget options failed to load.",
    fix: "Tap Fix all to rescan options.",
    href: "/options",
    label: "Open Options",
  },
  stock_opportunities: {
    message: "Stock swings failed to load.",
    fix: "Tap Fix all to rescan stocks.",
    href: "/stocks",
    label: "Open Stocks",
  },
  sports_opportunities: {
    message: "Sports plays failed to load.",
    fix: "Tap Fix all to rescan sports odds.",
    href: "/sports",
    label: "Open Sports",
  },
  list_parlays: {
    message: "Featured parlay failed to load.",
    fix: "Tap Fix all after a sports scan.",
    href: "/parlays",
    label: "Open Parlays",
  },
  breaking_news: {
    message: "Breaking news failed to load.",
    fix: "Tap Fix all to refresh news.",
    href: "/news",
    label: "Open News",
  },
  briefing_news: {
    message: "Briefing headlines failed to load.",
    fix: "Tap Fix all to refresh news.",
    href: "/news",
    label: "Open News",
  },
  performance_summary: {
    message: "Performance summary failed to load.",
    fix: "Tap Fix all to grade/backfill.",
    href: "/performance",
    label: "Open Performance",
  },
};

const ERROR_CODES = new Set([
  "top_opportunities",
  "budget_opportunities",
  "stock_opportunities",
  "sports_opportunities",
]);

function severityFromLegacy(raw: string, code: string): WarningSeverity {
  if (ERROR_CODES.has(code)) return "error";
  // Soft maintenance / timeouts / secondary reads never count as partial load.
  const lower = raw.toLowerCase();
  if (
    lower.includes("timed out")
    || lower.includes("auto-refreshed")
    || code.startsWith("expire_stale")
    || code.startsWith("signal_backfill")
    || code.startsWith("resolve_outcomes")
    || code.startsWith("market_intelligence")
    || code.startsWith("atlas_briefing")
    || code.startsWith("news")
    || code.startsWith("list_parlays")
    || code.startsWith("breaking_news")
    || code.startsWith("briefing_news")
    || code.startsWith("performance_summary")
    || code.startsWith("tracking_stats")
    || code.startsWith("unread_alerts")
    || code.startsWith("catalyst")
  ) {
    return "info";
  }
  return "info";
}

function parseLegacyString(raw: string): DashboardWarning {
  const trimmed = raw.trim();
  const code = trimmed.split(":")[0]?.trim() || "unknown";
  const hint = LEGACY_HINTS[code];
  const detail = trimmed.includes(":") ? trimmed.slice(trimmed.indexOf(":") + 1).trim() : undefined;
  return {
    code,
    severity: severityFromLegacy(trimmed, code),
    message: hint?.message || trimmed,
    fix: hint?.fix || "Tap Fix all on Home.",
    detail: hint ? detail : undefined,
    action: hint?.href
      ? { label: hint.label || "Open", href: hint.href }
      : { label: "Fix all", href: "/" },
  };
}

export function normalizeDashboardWarnings(raw: unknown): DashboardWarning[] {
  if (!Array.isArray(raw)) return [];
  const out: DashboardWarning[] = [];
  for (const item of raw) {
    if (typeof item === "string") {
      if (item.includes("auto-refreshed stale headlines")) continue;
      out.push(parseLegacyString(item));
      continue;
    }
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const code = String(obj.code || "unknown");
      let severity = (["info", "warn", "error"].includes(String(obj.severity))
        ? String(obj.severity)
        : "info") as WarningSeverity;
      // Harden: never treat soft codes as partial-load drivers even if API is old.
      if (!ERROR_CODES.has(code) && severity !== "error") {
        severity = "info";
      }
      const message = String(obj.message || code);
      const fix = String(obj.fix || "Tap Fix all on Home.");
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
        repair: obj.repair != null ? String(obj.repair) : undefined,
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

/** Only core board load failures drive "partial load". */
export function actionableWarnings(warnings: DashboardWarning[]): DashboardWarning[] {
  return warnings.filter((w) => w.severity === "error");
}

export function softNotices(warnings: DashboardWarning[]): DashboardWarning[] {
  return warnings.filter((w) => w.severity !== "error");
}
