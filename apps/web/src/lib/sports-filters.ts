import type { SportsSignal } from "@/components/sports/SportsSignalCard";

export type SportsSortKey =
  | "soonest"
  | "opportunity"
  | "edge"
  | "ev"
  | "confidence"
  | "risk_low";
export type SportsFilterKey = "all" | "moneyline" | "spread" | "total" | "steam" | "value";
export type SportsWindowKey = "soon" | "week";

const NEAR_TERM_HOURS = 48;
const WEEK_HOURS = 168;

function getEdge(row: SportsSignal): number {
  return Number(row.line_movement?.edge_pct ?? row.context?.edge_pct ?? 0);
}

function getEv(row: SportsSignal): number {
  return Number(row.expected_value ?? row.context?.expected_value ?? 0);
}

function getSoonest(row: SportsSignal): number {
  return row.hours_until_start ?? 9999;
}

function compositeRank(row: SportsSignal): number {
  const opp = row.opportunity_score ?? 0;
  const edge = getEdge(row);
  const hours = getSoonest(row);
  const soonBoost = hours <= 24 ? 12 : hours <= NEAR_TERM_HOURS ? 8 : 0;
  const latePenalty = hours > NEAR_TERM_HOURS ? Math.min(20, (hours - NEAR_TERM_HOURS) * 0.12) : 0;
  return opp + soonBoost + edge * 0.35 - latePenalty;
}

export function filterByWindow(items: SportsSignal[], window: SportsWindowKey): SportsSignal[] {
  if (window === "week") {
    return items.filter((i) => (i.hours_until_start ?? 9999) <= WEEK_HOURS);
  }
  return items.filter((i) => (i.hours_until_start ?? 9999) <= NEAR_TERM_HOURS);
}

export function filterSports(items: SportsSignal[], filter: SportsFilterKey): SportsSignal[] {
  switch (filter) {
    case "moneyline":
      return items.filter((i) => i.bet_type === "moneyline");
    case "spread":
      return items.filter((i) => i.bet_type === "spread");
    case "total":
      return items.filter((i) => i.bet_type === "total");
    case "steam":
      return items.filter(
        (i) => (i.sharp_indicator ?? i.context?.sharp_indicator) === "steam",
      );
    case "value":
      return items.filter(
        (i) => (i.sharp_indicator ?? i.context?.sharp_indicator) === "value",
      );
    default:
      return items;
  }
}

export function sortSports(items: SportsSignal[], sort: SportsSortKey): SportsSignal[] {
  const copy = [...items];
  copy.sort((a, b) => {
    switch (sort) {
      case "soonest":
        return getSoonest(a) - getSoonest(b) || compositeRank(b) - compositeRank(a);
      case "opportunity":
        return compositeRank(b) - compositeRank(a);
      case "edge":
        return getEdge(b) - getEdge(a);
      case "ev":
        return getEv(b) - getEv(a);
      case "confidence":
        return b.confidence_score - a.confidence_score;
      case "risk_low":
        return a.risk_score - b.risk_score;
      default:
        return 0;
    }
  });
  return copy;
}

export function filterBySport(items: SportsSignal[], sportKey: string | null): SportsSignal[] {
  if (!sportKey) return items;
  const norm = sportKey.toLowerCase();
  return items.filter((i) => i.sport.toLowerCase().replace(/\s+/g, "_") === norm);
}
