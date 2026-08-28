/**
 * Credit safety: Rescore must send cache_only (0 Odds credits).
 * Scan uses premium_scan (server may live-seed missing Tonight leagues).
 * Only Fetch (force_refresh) may spend directly from the client.
 * Repair uses /engine/repair-sports (server decides cache vs one live seed).
 * Run with: npx --yes tsx apps/web/src/lib/sports-scan-flags.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "../components/sports/SportsSignalsView.tsx"), "utf8");

assert.match(
  source,
  /mode === "scan"[\s\S]*?params\.set\("premium_scan", "true"\)/,
  "Scan must send premium_scan",
);
assert.match(
  source,
  /mode === "rescore"[\s\S]*?params\.set\("cache_only", "true"\)/,
  "Rescore must send cache_only",
);
assert.match(
  source,
  /mode === "live"[\s\S]*?params\.set\("force_refresh", "true"\)/,
  "Fetch must send force_refresh",
);
assert.match(
  source,
  /globalThis\.confirm\(/,
  "Fetch/Repair must confirm before spending credits",
);
assert.match(
  source,
  /\/engine\/repair-sports/,
  "Repair sports board must call /engine/repair-sports",
);
assert.match(
  source,
  /Repair sports board/,
  "Sports UI must expose Repair sports board",
);
assert.match(
  source,
  /readSportsBoardCache\(\)\?\.window \?\? "today"/,
  "Sports board must default Window to Today",
);
assert.match(
  source,
  /setWindow\("today"\)/,
  "Scan/Repair must pin the Window to Today, not auto-widen to Next 48h",
);
assert.doesNotMatch(
  source,
  /pickWindowWithResults/,
  "Sports view must not auto-widen Today to Next 48h",
);
{
  const repairStart = source.indexOf("async function repairSportsBoard");
  const insightStart = source.indexOf("async function refreshOpenAiPicks");
  assert.ok(repairStart >= 0 && insightStart > repairStart, "repair and insight functions exist");
  const repairFn = source.slice(repairStart, insightStart);
  assert.doesNotMatch(
    repairFn,
    /refreshOpenAiPicks\(/,
    "Repair must not chain Atlas Insight (that flipped the Window off Today)",
  );
}
assert.match(
  source,
  /replaceEmpty:\s*created > 0/,
  "Scan must not force-clear the board when zero plays were saved",
);
assert.match(
  source,
  /Always reload after Repair/,
  "Repair must reload the board even when ok=false",
);
assert.match(
  source,
  /Odds cache is empty — Scan needs a one-time Repair/,
  "Cold cache Scan must route into Repair",
);
assert.match(
  source,
  /Odds cache is empty/,
  "Sports UI must surface empty odds cache banner",
);

console.log("sports-scan-flags.test.ts: ok");
