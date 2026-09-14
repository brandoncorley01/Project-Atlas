/**
 * Sports ET time helpers — run with:
 *   npx --yes tsx --tsconfig apps/web/tsconfig.json apps/web/src/lib/sports-time.test.ts
 */
import {
  easternDayKey,
  formatSportsKickoffET,
  sportsSlateDayKey,
  sportsTodayLabelET,
} from "./sports-time.ts";

function assert(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg);
}

// Monday 10 PM Eastern = Tuesday 02:00 UTC — must still format as Monday in ET.
const mondayNightEt = "2026-08-31T22:00:00-04:00";
const kickoff = formatSportsKickoffET(mondayNightEt);
assert(kickoff.includes("Mon"), `expected Monday in ET kickoff, got ${kickoff}`);
assert(kickoff.includes("Aug"), `expected August in ET kickoff, got ${kickoff}`);
assert(!kickoff.includes("Tue"), `must not show Tuesday for Monday ET game: ${kickoff}`);

assert(
  easternDayKey(mondayNightEt) === easternDayKey(new Date("2026-08-31T22:00:00-04:00")),
  "easternDayKey stable",
);

const label = sportsTodayLabelET(new Date("2026-08-31T21:00:00-04:00"));
assert(label.includes("Mon") && label.includes("Aug"), `expected Mon Aug slate label, got ${label}`);

// Sports day rolls at 6am ET — 1:05 AM Tuesday is still Monday's slate.
const monEve = new Date("2026-08-31T21:00:00-04:00");
const tueEarly = new Date("2026-09-01T01:05:00-04:00");
const tueAfternoon = new Date("2026-09-01T15:00:00-04:00");
assert(
  sportsSlateDayKey(monEve) === sportsSlateDayKey(tueEarly),
  "early-AM Tuesday shares Monday sports-day key",
);
assert(
  sportsSlateDayKey(monEve) !== sportsSlateDayKey(tueAfternoon),
  "Tuesday afternoon is the next sports day",
);

console.log("sports-time.test.ts: ok");
