import type { SportsSignal } from "@/components/sports/SportsSignalCard";

/** Static fixture for layout verification — no API / scan credits used. */
export const MOBILE_LAYOUT_PREVIEW_SIGNAL: SportsSignal = {
  id: "preview-padres-spread",
  sport: "baseball_mlb",
  event_name: "Arizona Diamondbacks @ San Diego Padres",
  event_start: "2026-07-09T21:41:00Z",
  bet_type: "spread",
  selection: "San Diego Padres +1.5",
  odds_american: -110,
  odds_decimal: 1.91,
  expected_value: 4.2,
  recommendation: "Spread — San Diego Padres +1.5 - Wed Jul 9 · FanDuel -110",
  explanation: "Preview card for mobile layout checks only.",
  confidence_score: 72,
  risk_score: 41,
  opportunity_score: 88,
  categories: ["starting_soon", "top_picks"],
  hours_until_start: 0.2,
  data_as_of_label: "Wed Jul 09, 01:27",
  book_odds: [
    { key: "fanduel", title: "FanDuel", american: -110, is_primary: true },
    { key: "draftkings", title: "DraftKings", american: -112 },
  ],
};
