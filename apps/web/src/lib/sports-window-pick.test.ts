/**
 * pickWindowWithResults still widens off empty preferred windows.
 * Sports UI pins Today after Scan (Today includes ≤24h tips) — see sports-scan-flags.test.ts.
 * Run with: npx --yes tsx --tsconfig apps/web/tsconfig.json apps/web/src/lib/sports-window-pick.test.ts
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
  "30h tips widen off empty Today to Next 48h",
);

const tonight = [row(3, "tonight")];
assert.equal(pickWindowWithResults(tonight, "today"), "today");

const next24Only = [row(20, "twenty")];
assert.equal(
  pickWindowWithResults(next24Only, "today"),
  "today",
  "≤24h tips count as Today so the window does not jump",
);

const empty: SportsSignal[] = [];
assert.equal(pickWindowWithResults(empty, "today"), "today");

console.log("sports-window-pick.test.ts: ok");
