/**
 * Sports board filter smoke tests — run with:
 *   npx --yes tsx apps/web/src/lib/sports-filters.test.ts
 */
import {
  dedupeOneSidePerMarket,
  filterBySport,
  filterByWindow,
  filterSports,
  hoursUntilStart,
  isSportsCalendarToday,
  sortSports,
  type SportsSignal,
} from "./sports-filters.ts";

function hoursFromNow(h: number): string {
  return new Date(Date.now() + h * 3600e3).toISOString();
}

/** Kickoff later today in America/New_York (avoids crossing midnight in tests). */
function laterTodayEastern(): { iso: string; hours: number } {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const hour = Number(parts.find((p) => p.type === "hour")?.value || "0");
  if (hour >= 22) {
    return { iso: hoursFromNow(0.5), hours: 0.5 };
  }
  const hours = Math.max(1, 23 - hour);
  return { iso: hoursFromNow(hours), hours };
}

function row(partial: Partial<SportsSignal> & { id: string }): SportsSignal {
  return {
    sport: "MLB",
    bet_type: "moneyline",
    selection: "Home",
    event_name: "Away @ Home",
    opportunity_score: 50,
    confidence_score: 50,
    risk_score: 40,
    odds_american: -110,
    scoring_snapshot: {},
    line_movement: {},
    ...partial,
  } as SportsSignal;
}

const todayKick = laterTodayEastern();
const fixtures: SportsSignal[] = [
  row({
    id: "today",
    event_start: todayKick.iso,
    hours_until_start: todayKick.hours,
    sport: "WNBA",
    opportunity_score: 60,
  }),
  row({
    id: "soon",
    event_start: hoursFromNow(30),
    hours_until_start: 30,
    sport: "MLS",
    opportunity_score: 55,
  }),
  row({
    id: "week",
    event_start: hoursFromNow(100),
    hours_until_start: 100,
    sport: "EPL",
    opportunity_score: 70,
  }),
  row({
    id: "month",
    event_start: hoursFromNow(400),
    hours_until_start: 400,
    sport: "NFL",
    opportunity_score: 65,
  }),
  row({
    id: "beyond",
    event_start: hoursFromNow(900),
    hours_until_start: 900,
    sport: "EPL",
    opportunity_score: 80,
  }),
  row({
    id: "futures",
    bet_type: "futures",
    event_start: hoursFromNow(2000),
    hours_until_start: 2000,
    sport: "NFL",
    selection: "Chiefs",
    opportunity_score: 40,
  }),
  row({
    id: "undated-insight",
    hours_until_start: null,
    event_start: undefined,
    openai_web: true,
    pick_source: "openai_web",
    scoring_snapshot: { source: "openai_web", openai_web: true },
    sport: "MMA",
    opportunity_score: 58,
  }),
  row({
    id: "missing-hours",
    event_start: hoursFromNow(10),
    sport: "Boxing",
    opportunity_score: 52,
  } as SportsSignal),
];

function ids(list: SportsSignal[]) {
  return list.map((r) => r.id).sort();
}

function assert(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg);
}

const todayRow = fixtures[0];
if (!isSportsCalendarToday(todayRow)) {
  assert(filterByWindow([todayRow], "soon").length === 1, "late-night kickoff still in soon");
}

assert(hoursUntilStart(fixtures[7]) != null && (hoursUntilStart(fixtures[7]) as number) > 0, "derive hours");

const today = filterByWindow(fixtures, "today");
if (isSportsCalendarToday(todayRow)) {
  assert(today.some((r) => r.id === "today"), "today includes kickoff today");
}
assert(today.some((r) => r.id === "undated-insight"), "today keeps undated insight");
assert(!today.some((r) => r.id === "week"), "today excludes week games");

const soon = filterByWindow(fixtures, "soon");
assert(soon.some((r) => r.id === "today") && soon.some((r) => r.id === "soon"), "soon has 48h");
assert(soon.some((r) => r.id === "missing-hours"), "soon derives missing hours");
assert(!soon.some((r) => r.id === "week"), "soon excludes 100h");

const week = filterByWindow(fixtures, "week");
assert(week.some((r) => r.id === "week") && !week.some((r) => r.id === "month"), "week bounds");

const month = filterByWindow(fixtures, "month");
assert(month.some((r) => r.id === "month") && !month.some((r) => r.id === "beyond"), "month bounds");
assert(month.some((r) => r.id === "futures"), "month keeps futures");

const futuresWin = filterByWindow(fixtures, "futures");
assert(futuresWin.some((r) => r.id === "futures") && futuresWin.some((r) => r.id === "beyond"), "futures window");
assert(!futuresWin.some((r) => r.id === "today"), "futures excludes today games");

const all = filterByWindow(fixtures, "all");
assert(all.length === fixtures.length, "all keeps upcoming");

const mlbOnly = filterBySport(
  [row({ id: "a", sport: "MLB" }), row({ id: "b", sport: "WNBA" })],
  "MLB",
);
assert(ids(mlbOnly).join() === "a", "league filter");

const moneylineOnly = filterSports(
  [row({ id: "ml", bet_type: "moneyline" }), row({ id: "sp", bet_type: "spread" })],
  "moneyline",
);
assert(ids(moneylineOnly).join() === "ml", "bet type filter");

const sorted = sortSports(
  [
    row({ id: "low", opportunity_score: 20, hours_until_start: 50 }),
    row({ id: "high", opportunity_score: 90, hours_until_start: 50 }),
  ],
  "opportunity",
);
assert(sorted[0].id === "high", "opportunity sort");

const deduped = dedupeOneSidePerMarket([
  row({ id: "a", event_name: "X", bet_type: "moneyline", selection: "Home", opportunity_score: 40 }),
  row({ id: "b", event_name: "X", bet_type: "moneyline", selection: "Away", opportunity_score: 70 }),
]);
assert(deduped.length === 1 && deduped[0].id === "b", "dedupe keeps stronger side");

console.log("sports-filters ok", {
  today: ids(today),
  soon: ids(soon),
  week: ids(week),
  month: ids(month),
  futures: ids(futuresWin),
  all: all.length,
});
