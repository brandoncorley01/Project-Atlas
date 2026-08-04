/**
 * Dashboard warning normalization — run with:
 *   npx --yes tsx --tsconfig apps/web/tsconfig.json apps/web/src/lib/dashboard-warnings.test.ts
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
]);
assert(dropped.length === 1, `expected 1 warning after dropping noise, got ${dropped.length}`);
assert(dropped[0].code === "atlas_briefing", `expected atlas_briefing, got ${dropped[0].code}`);
assert(dropped[0].severity === "info", `expected info, got ${dropped[0].severity}`);

const structured = normalizeDashboardWarnings([
  {
    code: "sports_opportunities",
    severity: "error",
    message: "Sports plays failed to load.",
    fix: "Retry Home. If empty, open Sports and Scan sports odds.",
    detail: "timeout",
    action: { label: "Open Sports", href: "/sports" },
  },
  {
    code: "atlas_briefing",
    severity: "info",
    message: "AI briefing timed out",
    fix: "Tap Refresh",
  },
]);
const actionable = actionableWarnings(structured);
assert(actionable.length === 1, `expected 1 actionable, got ${actionable.length}`);
assert(actionable[0].action?.href === "/sports", "expected sports action href");
assert(/Scan sports/i.test(actionable[0].fix), "expected fix guidance");

console.log("dashboard-warnings.test.ts: ok");
