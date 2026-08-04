/**
 * Dashboard warning normalization — run with:
 *   npx --yes tsx apps/web/src/lib/dashboard-warnings.test.ts
 */
import {
  actionableWarnings,
  normalizeDashboardWarnings,
} from "./dashboard-warnings";

function assert(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg);
}

const dropped = normalizeDashboardWarnings([
  "news: auto-refreshed stale headlines for briefing",
  "atlas_briefing: timed out (template only)",
  "news_auto_refresh: timed out (using cached headlines)",
  "list_parlays: boom",
]);
assert(dropped.length === 3, `expected 3 soft notices, got ${dropped.length}`);
assert(
  dropped.every((w) => w.severity === "info"),
  "legacy soft strings must be info (not partial load)",
);
assert(actionableWarnings(dropped).length === 0, "no actionable from soft legacy");

const structured = normalizeDashboardWarnings([
  {
    code: "sports_opportunities",
    severity: "error",
    message: "Sports plays failed to load.",
    fix: "Tap Fix all to rescan sports odds.",
    detail: "timeout",
    action: { label: "Open Sports", href: "/sports" },
  },
  {
    code: "breaking_news",
    severity: "warn",
    message: "Breaking news failed",
    fix: "Tap Fix all",
  },
]);
const actionable = actionableWarnings(structured);
assert(actionable.length === 1, `expected 1 actionable, got ${actionable.length}`);
assert(structured[1].severity === "info", "non-error soft codes forced to info");
assert(/Fix all/i.test(actionable[0].fix), "expected Fix all guidance");

console.log("dashboard-warnings.test.ts: ok");
