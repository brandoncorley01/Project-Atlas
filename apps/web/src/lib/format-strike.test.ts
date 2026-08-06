import assert from "node:assert/strict";
import { formatStrike } from "./format-strike.ts";

assert.equal(formatStrike(18), "18");
assert.equal(formatStrike(18.0), "18");
assert.equal(formatStrike(18.5), "18.5");
assert.equal(formatStrike(19.5), "19.5");
assert.equal(formatStrike(232.5), "232.5");
assert.equal(formatStrike(735), "735");
assert.notEqual(formatStrike(18.0), formatStrike(18.5));

console.log("format-strike tests passed");
