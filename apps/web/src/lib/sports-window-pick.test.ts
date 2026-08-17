/**
 * pickWindowWithResults must not hide a successful Scan behind empty Today.
 * Repair must NOT use this helper — it pins Today so a missing Tonight slate stays visible.
 * Run with: npx --yes tsx apps/web/src/lib/sports-window-pick.test.ts
 */
import assert from "node:assert/strict";
import { pickWindowWithResults, type SportsWindowKey } from "./sports-filters.ts";
import type { SportsSignal } from "../components/sports/SportsSignalCard.tsx";

function row(hoursFromNow: number, id: string): SportsSignal {
  const start = new Date(Date.now() + hoursFromNow * 3600_000).toISOString();
  return {
    id,
    sport: "MLB",
    event_name: `${id} game`,
    event_start: start,
    bet_type: "moneyline",
    selection: "Home",
    opportunity_score: 40,
  } as SportsSignal;
}

const tomorrowOnly = [row(30, "tmr")];
assert.equal(
  pickWindowWithResults(tomorrowOnly, "today" as SportsWindowKey),
  "soon",
  "tomorrow picks must widen off empty Today",
);

const tonight = [row(3, "tonight")];
assert.equal(pickWindowWithResults(tonight, "today"), "today");

const empty: SportsSignal[] = [];
assert.equal(pickWindowWithResults(empty, "today"), "today");

console.log("sports-window-pick.test.ts: ok");
