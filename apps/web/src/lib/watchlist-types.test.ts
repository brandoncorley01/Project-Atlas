/**
 * Watchlist → performance tracking smoke tests — run with:
 *   npx --yes tsx apps/web/src/lib/watchlist-types.test.ts
 */
import {
  effectiveItemType,
  performanceTrackingForItem,
  type WatchlistItem,
} from "./watchlist-types";

let failed = 0;

function assert(cond: unknown, msg: string) {
  if (!cond) {
    failed += 1;
    console.error("FAIL:", msg);
  } else {
    console.log("ok:", msg);
  }
}

{
  const item: WatchlistItem = {
    id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    item_type: "ticker",
    symbol: "AAPL",
    metadata: {
      option_type: "call",
      underlying: "AAPL",
      strike: 200,
      expiration: "2026-08-15",
      label: "AAPL CALL $200",
    },
  };
  assert(effectiveItemType(item) === "option_signal", "legacy option fields → option_signal");
  const tracking = performanceTrackingForItem(item);
  assert(tracking?.module === "options", "legacy option tracks as options module");
  assert(
    tracking?.signalId === "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "legacy option falls back to watchlist row id",
  );
}

{
  const item: WatchlistItem = {
    id: "11111111-2222-3333-4444-555555555555",
    item_type: "ticker",
    symbol: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    metadata: {
      watchlist_kind: "option_signal",
      signal_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      underlying: "TSLA",
      option_type: "put",
      strike: 250,
    },
  };
  assert(effectiveItemType(item) === "option_signal", "modern option_signal kind");
  const tracking = performanceTrackingForItem(item);
  assert(tracking?.module === "options", "modern option module");
  assert(
    tracking?.signalId === "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "modern option uses signal_id",
  );
  assert(tracking?.signalSnapshot?.user_tracked === true, "snapshot marks user_tracked");
}

{
  const item: WatchlistItem = {
    id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    item_type: "ticker",
    symbol: "MSFT",
    metadata: {},
  };
  assert(performanceTrackingForItem(item) === null, "plain ticker is not trackable");
}

if (failed > 0) {
  console.error(`\n${failed} assertion(s) failed`);
  process.exit(1);
}
console.log("\nAll watchlist-types checks passed");
