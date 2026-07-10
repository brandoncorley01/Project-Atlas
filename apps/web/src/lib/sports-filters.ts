import type { SportsSignal } from "@/components/sports/SportsSignalCard";

export type SportsSortKey =
  | "soonest"
  | "opportunity"
  | "edge"
  | "ev"
  | "confidence"
  | "risk_low";
export type SportsFilterKey =
  | "all"
  | "moneyline"
  | "spread"
  | "total"
  | "futures"
  | "steam"
  | "value";
export type SportsWindowKey = "soon" | "week" | "month" | "futures" | "all";

const NEAR_TERM_HOURS = 48;
const WEEK_HOURS = 168;
const MONTH_HOURS = 720;

function getEdge(row: SportsSignal): number {
  return Number(row.line_movement?.edge_pct ?? row.context?.edge_pct ?? 0);
}

function getEv(row: SportsSignal): number {
  return Number(row.expected_value ?? row.context?.expected_value ?? 0);
}

function getSoonest(row: SportsSignal): number {
  return row.hours_until_start ?? 9999;
}

function isFutures(row: SportsSignal): boolean {
  const bet = (row.bet_type || "").toLowerCase();
  return bet === "futures" || bet === "outright";
}

function compositeRank(row: SportsSignal): number {
  const opp = row.opportunity_score ?? 0;
  const edge = getEdge(row);
  const hours = getSoonest(row);
  const soonBoost = hours <= 24 ? 12 : hours <= NEAR_TERM_HOURS ? 8 : hours <= WEEK_HOURS ? 2 : 0;
  const latePenalty =
    !isFutures(row) && hours > NEAR_TERM_HOURS
      ? Math.min(12, (hours - NEAR_TERM_HOURS) * 0.04)
      : 0;
  return opp + soonBoost + edge * 0.35 - latePenalty;
}

export function filterByWindow(items: SportsSignal[], window: SportsWindowKey): SportsSignal[] {
  const started = items.filter((i) => (i.hours_until_start ?? 0) <= 0);
  if (window === "all") {
    return items;
  }
  if (window === "futures") {
    return items.filter((i) => isFutures(i) || (i.hours_until_start ?? 0) > WEEK_HOURS);
  }
  if (window === "month") {
    const upcoming = items.filter((i) => {
      const h = i.hours_until_start ?? 9999;
      return (h > 0 && h <= MONTH_HOURS) || isFutures(i);
    });
    return [...started, ...upcoming];
  }
  if (window === "week") {
    const upcoming = items.filter((i) => {
      const h = i.hours_until_start ?? 9999;
      return h > 0 && h <= WEEK_HOURS;
    });
    return [...started, ...upcoming];
  }
  const upcoming = items.filter((i) => {
    const h = i.hours_until_start ?? 9999;
    return h > 0 && h <= NEAR_TERM_HOURS && !isFutures(i);
  });
  return [...started, ...upcoming];
}

export function filterSports(items: SportsSignal[], filter: SportsFilterKey): SportsSignal[] {
  switch (filter) {
    case "moneyline":
      return items.filter((i) => i.bet_type === "moneyline");
    case "spread":
      return items.filter((i) => i.bet_type === "spread");
    case "total":
      return items.filter((i) => i.bet_type === "total");
    case "futures":
      return items.filter((i) => isFutures(i));
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
  const norm = sportKey.toLowerCase().replace(/\s+/g, "_");
  return items.filter((i) => {
    const itemNorm = i.sport.toLowerCase().replace(/\s+/g, "_");
    if (itemNorm === norm) return true;
    // Allow "tennis" tab to match "ATP Wimbledon" / "WTA ..." labels
    if (norm === "tennis" && (itemNorm.includes("atp") || itemNorm.includes("wta") || itemNorm.includes("tennis"))) {
      return true;
    }
    if (norm === "mma" && (itemNorm.includes("mma") || itemNorm.includes("ufc"))) {
      return true;
    }
    return itemNorm.includes(norm) || norm.includes(itemNorm);
  });
}

function marketFamilyKey(row: SportsSignal): string {
  const snap = (row as SportsSignal & { scoring_snapshot?: { event_id?: string } }).scoring_snapshot;
  const eventId =
    snap?.event_id ||
    (row.line_movement as { event_id?: string } | undefined)?.event_id ||
    row.event_name ||
    row.id;
  const betType = (row.bet_type || "moneyline").toLowerCase();
  return `${eventId}|${betType}`;
}

/** Drop alternate sides of the same event+market so the board never shows both ML/spread/total sides. */
export function dedupeOneSidePerMarket(items: SportsSignal[]): SportsSignal[] {
  if (items.length <= 1) return items;
  const best = new Map<string, SportsSignal>();
  const order: string[] = [];
  for (const row of items) {
    const key = marketFamilyKey(row);
    const prev = best.get(key);
    if (!prev) {
      best.set(key, row);
      order.push(key);
      continue;
    }
    if (compositeRank(row) > compositeRank(prev)) {
      best.set(key, row);
    }
  }
  return order.map((k) => best.get(k)!).filter(Boolean);
}
