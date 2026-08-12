/**
 * Credit safety: Scan and Rescore must send cache_only (0 Odds credits).
 * Only Fetch (force_refresh) may spend.
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
  /mode === "scan" \|\| mode === "rescore"[\s\S]*?params\.set\("cache_only", "true"\)/,
  "Scan and Rescore must send cache_only",
);
assert.match(
  source,
  /mode === "live"[\s\S]*?params\.set\("force_refresh", "true"\)/,
  "Fetch must send force_refresh",
);
assert.match(
  source,
  /globalThis\.confirm\(/,
  "Fetch must confirm before spending credits",
);
assert.match(
  source,
  /replaceEmpty:\s*created > 0 \|\| Boolean\(kept\)/,
  "Scan must not force-clear the board when zero plays were saved",
);

console.log("sports-scan-flags.test.ts: ok");
