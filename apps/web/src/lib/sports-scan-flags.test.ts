/**
 * Regression: Scan sports odds must not send cache_only (blocks cold live-seed).
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
  /mode === "rescore"[\s\S]*?params\.set\("cache_only", "true"\)/,
  "Rescore should still send cache_only",
);
assert.doesNotMatch(
  source,
  /mode === "scan" && cacheRescoreFree/,
  "Scan must not gate cache_only on cacheRescoreFree",
);
assert.match(
  source,
  /replaceEmpty:\s*created > 0 \|\| Boolean\(kept\)/,
  "Scan must not force-clear the board when zero plays were saved",
);

console.log("sports-scan-flags.test.ts: ok");
