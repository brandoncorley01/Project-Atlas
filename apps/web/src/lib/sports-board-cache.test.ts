/**
 * Sports board cache helpers — run with:
 *   npx --yes tsx apps/web/src/lib/sports-board-cache.test.ts
 */
import {
  boardAsOfFromItems,
  formatRelativeAgo,
  hydrateSportsItems,
} from "./sports-board-cache.ts";
import type { SportsSignal } from "../components/sports/SportsSignalCard.tsx";

function assert(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg);
}

function row(id: string, data_as_of?: string): SportsSignal {
  return {
    id,
    module: "sports",
    title: id,
    recommendation: "buy",
    scores: { confidence: 50, risk: 20, opportunity: 60 },
    data_as_of,
  } as SportsSignal;
}

const asOf = boardAsOfFromItems([
  row("a", "2026-08-01T10:00:00.000Z"),
  row("b", "2026-08-09T18:00:00.000Z"),
  row("c"),
]);
assert(asOf === "2026-08-09T18:00:00.000Z", `expected newest board as-of, got ${asOf}`);

assert(formatRelativeAgo(new Date().toISOString()) === "just now", "expected just now");
assert(formatRelativeAgo(null) === null, "expected null for missing");

// Without sessionStorage (node), hydrate falls back to server items or [].
const hydrated = hydrateSportsItems([row("x", "2026-08-09T12:00:00.000Z")]);
assert(hydrated.length === 1 && hydrated[0].id === "x", "hydrate should keep server items");

const emptyHydrate = hydrateSportsItems([]);
assert(Array.isArray(emptyHydrate), "empty hydrate returns array");

console.log("sports-board-cache.test.ts: ok");
