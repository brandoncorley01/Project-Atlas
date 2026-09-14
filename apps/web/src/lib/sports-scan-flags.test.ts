/**
 * Credit safety: Rescore must send cache_only (0 Odds credits).
 * Scan uses premium_scan (server may live-seed missing Tonight leagues when needed).
 * Only Fetch (force_refresh) may spend directly from the client.
 * When Today is empty, Scan must open Next 24h / 48h via pickWindowWithResults.
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
  /\.confirm\(/,
  "Fetch must confirm before spending credits",
);
assert.doesNotMatch(
  source,
  /repairSportsBoard/,
  "Sports UI must not auto-run or expose Repair sports board",
);
assert.doesNotMatch(
  source,
  /\/engine\/repair-sports/,
  "Sports view must not call /engine/repair-sports",
);
assert.match(
  source,
  /readSportsBoardCache\(\)\?\.window \?\? "today"/,
  "Sports board must default Window to Today",
);
assert.match(
  source,
  /pickWindowWithResults/,
  "Sports view must widen off empty Today via pickWindowWithResults",
);
assert.match(
  source,
  /applyWindowForBoard\("today"\)/,
  "Scan/reload must applyWindowForBoard so empty Today opens Next 24h/48h",
);
assert.doesNotMatch(
  source,
  /setWindow\("today"\)/,
  "Sports view must not hard-pin empty Today after Scan",
);
assert.match(
  source,
  /replaceEmpty:\s*created > 0/,
  "Scan must not force-clear the board when zero plays were saved",
);
assert.match(
  source,
  /Odds cache is empty/,
  "Sports UI must surface empty odds cache banner",
);
assert.match(
  source,
  /isApiWakingResponse/,
  "Scan must detect Render cold-start responses and retry",
);
assert.match(
  source,
  /API is waking up — retrying Scan/,
  "Scan must show a wake-and-retry message on cold start",
);
assert.match(
  source,
  /300_000|300000/,
  "Scan client timeout must cover BFF wake + long engine budget",
);

console.log("sports-scan-flags.test.ts: ok");
