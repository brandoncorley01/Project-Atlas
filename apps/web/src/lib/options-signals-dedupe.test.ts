/**
 * Options page must not list the same signal in both budget and "All" sections
 * when capital-first mode persists only under-$100 rows.
 */
import assert from "node:assert/strict";
import {
  exclusiveAllOptions,
  isCapitalFirstOnlyBoard,
} from "./options-signals-dedupe.ts";

const one = [{ id: "sig-1" }] as never;
const both = [{ id: "sig-1" }, { id: "sig-2" }] as never;
const budgetOne = [{ id: "sig-1" }] as never;

// Production bug: one budget row returned by both list endpoints → shown twice.
assert.deepEqual(exclusiveAllOptions(one, budgetOne), []);
assert.equal(isCapitalFirstOnlyBoard(one, budgetOne), true);

assert.deepEqual(exclusiveAllOptions(both, budgetOne), [{ id: "sig-2" }]);
assert.equal(isCapitalFirstOnlyBoard(both, budgetOne), false);

assert.deepEqual(exclusiveAllOptions(both, [] as never), both);

console.log("options-signals-dedupe: ok");
