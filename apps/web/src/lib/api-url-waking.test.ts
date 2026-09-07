/**
 * Scan cold-start helpers.
 * Run with: npx --yes tsx apps/web/src/lib/api-url-waking.test.ts
 */
import assert from "node:assert/strict";
import { isApiWakingResponse } from "./api-url.ts";

assert.equal(isApiWakingResponse(503, { api_waking: true }), true);
assert.equal(
  isApiWakingResponse(503, { detail: "Atlas API is waking up (Render). Tap Scan again." }),
  true,
);
assert.equal(isApiWakingResponse(200, { ok: true }), false);
assert.equal(isApiWakingResponse(400, { detail: "bad request" }), false);
assert.equal(isApiWakingResponse(503, { detail: "quota exhausted" }), false);

console.log("api-url-waking.test.ts: ok");
