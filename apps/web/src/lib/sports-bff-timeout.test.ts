/**
 * BFF must give Repair the same long timeout as Scan/Fetch.
 * Run with: npx --yes tsx apps/web/src/lib/sports-bff-timeout.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "../app/api/atlas/[...path]/route.ts"), "utf8");

assert.match(
  source,
  /engine\/repair-sports/,
  "BFF must special-case engine/repair-sports",
);
assert.match(
  source,
  /ENGINE_LONG_PROXY_TIMEOUT_MS/,
  "Long engine timeout constant must exist",
);
assert.match(
  source,
  /subpath === "engine\/repair-sports"[\s\S]*?ENGINE_LONG_PROXY_TIMEOUT_MS|ENGINE_LONG_PROXY_TIMEOUT_MS[\s\S]*?repair-sports/,
  "repair-sports must use the long engine timeout",
);

console.log("sports-bff-timeout.test.ts: ok");
