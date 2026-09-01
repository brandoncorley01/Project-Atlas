import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import { easternDayKey } from "@/lib/sports-time";

export type SportsSortKey =
  | "soonest"
  | "opportunity"
  | "edge"
  | "ev"
  | "confidence"
  | "risk_low"
  | "openai"
  | "player_props";
export type SportsFilterKey =
  | "all"
  | "moneyline"
  | "spread"
  | "total"
  | "futures"
  | "steam"
  | "value"
  | "openai"
  | "my_bets"
  | "player_props";
export type SportsWindowKey = "today" | "next24h" | "soon" | "week" | "month" | "futures" | "all";

const NEAR_TERM_HOURS = 48;
const ROLLING_24H = 24;
const WEEK_HOURS = 168;
const MONTH_HOURS = 720;

export function isOpenAiSportsPick(row: SportsSignal): boolean {
  return Boolean(
    row.openai_web
      || row.pick_source === "openai_web"
      || row.scoring_snapshot?.source === "openai_web"
      || row.scoring_snapshot?.openai_web
      || row.line_movement?.source === "openai_web",
  );
}

export function isUserSportsPick(row: SportsSignal): boolean {
  return Boolean(
    row.user_entry
      || row.pick_source === "user_entry"
      || row.scoring_snapshot?.source === "user_entry"
      || row.scoring_snapshot?.user_entry
      || row.scoring_snapshot?.pick_origin === "user"
      || row.line_movement?.source === "user_entry",
  );
}

export function isPlayerPropPick(row: SportsSignal): boolean {
  const bet = (row.bet_type || "").toLowerCase();
  const propMarket = String(row.scoring_snapshot?.prop_market || "").toLowerCase();
  return (
    bet === "player_prop"
    || Boolean(row.scoring_snapshot?.is_player_prop)
    || Boolean(row.scoring_snapshot?.is_fight_prop)
    || propMarket.startsWith("fight_")
    || bet.startsWith("player_")
    || bet.startsWith("batter_")
    || bet.startsWith("pitcher_")
  );
}

function getEdge(row: SportsSignal): number {
  const edge = Number(row.line_movement?.edge_pct ?? row.context?.edge_pct ?? 0);
  // OpenAI consensus picks often have no Odds-API edge — fall back to opportunity so they sort.
  if (edge === 0 && isOpenAiSportsPick(row)) {
    return Number(row.opportunity_score ?? 0) * 0.08;
  }
  return edge;
}

function getEv(row: SportsSignal): number {
  const ev = Number(row.expected_value ?? row.context?.expected_value ?? 0);
  if (ev === 0 && isOpenAiSportsPick(row)) {
    return Number(row.opportunity_score ?? 0) * 0.05;
  }
  return ev;
}

/** Hours until kickoff — always prefer live clock from event_start when present. */
export function hoursUntilStart(row: SportsSignal): number | null {
  if (row.event_start) {
    try {
      const ms = new Date(row.event_start).getTime() - Date.now();
      if (Number.isFinite(ms)) return ms / 3_600_000;
    } catch {
      /* fall through */
    }
  }
  if (typeof row.hours_until_start === "number" && Number.isFinite(row.hours_until_start)) {
    return row.hours_until_start;
  }
  return null;
}

function getSoonest(row: SportsSignal): number {
  const hours = hoursUntilStart(row);
  if (hours != null) return hours;
  // Undated OpenAI picks stay visible near the top of "soonest" rather than sinking to 9999.
  if (isOpenAiSportsPick(row)) return 20;
  return 9999;
}

function isFutures(row: SportsSignal): boolean {
  const bet = (row.bet_type || "").toLowerCase();
  return bet === "futures" || bet === "outright";
}

/** Same Eastern calendar day as now — for Today parlays / sports window. */
export function isSportsCalendarToday(row: SportsSignal): boolean {
  if (!row.event_start || isFutures(row)) return false;
  const hours = hoursUntilStart(row);
  if (hours == null || hours <= 0) return false;
  try {
    return easternDayKey(row.event_start) === easternDayKey(new Date());
  } catch {
    return false;
  }
}

/** Card timing chip — calendar Today vs rolling Next 24h must not be conflated. */
export function kickoffWindowLabel(row: SportsSignal): { label: string; className: string } | null {
  const hours = hoursUntilStart(row);
  if (hours == null || hours <= 0) return null;
  if (isSportsCalendarToday(row)) {
    if (hours <= 6) {
      return { label: "Starting very soon", className: "bg-rose-500/20 text-rose-300" };
    }
    return { label: "Today", className: "bg-amber-500/20 text-amber-300" };
  }
  if (hours <= ROLLING_24H) {
    return { label: "Next 24h", className: "bg-orange-500/20 text-orange-300" };
  }
  if (hours <= NEAR_TERM_HOURS) {
    return { label: "Next 48h", className: "bg-emerald-500/20 text-emerald-300" };
  }
  if (hours <= WEEK_HOURS) {
    return { label: "This week", className: "bg-sky-500/20 text-sky-300" };
  }
  if (hours <= MONTH_HOURS) {
    return { label: "This month", className: "bg-violet-500/20 text-violet-300" };
  }
  return { label: "Futures window", className: "bg-violet-500/15 text-violet-200" };
}

function compositeRank(row: SportsSignal): number {
  const opp = row.opportunity_score ?? 0;
  const edge = getEdge(row);
  const hours = getSoonest(row);
  const soonBoost = isSportsCalendarToday(row)
    ? 12
    : hours <= ROLLING_24H
      ? 8
      : hours <= NEAR_TERM_HOURS
        ? 6
        : hours <= WEEK_HOURS
          ? 2
          : 0;
  const latePenalty =
    !isFutures(row) && hours > NEAR_TERM_HOURS
      ? Math.min(12, (hours - NEAR_TERM_HOURS) * 0.04)
      : 0;
  const todayBoost = isSportsCalendarToday(row) ? 4 : 0;
  const openaiBoost = isOpenAiSportsPick(row) ? 3 : 0;
  return opp + soonBoost + edge * 0.35 - latePenalty + todayBoost + openaiBoost;
}

export function filterByWindow(items: SportsSignal[], window: SportsWindowKey): SportsSignal[] {
  // Concluded / in-progress games leave the live board — keep only upcoming (or undated Insight/user).
  const live = items.filter((i) => {
    const h = hoursUntilStart(i);
    return h == null || h > 0;
  });
  const undatedInsightOrUser = (i: SportsSignal) =>
    (isOpenAiSportsPick(i) || isUserSportsPick(i)) && hoursUntilStart(i) == null;

  if (window === "all") {
    return live;
  }
  if (window === "today") {
    return live.filter((i) => {
      if (undatedInsightOrUser(i)) return true;
      if (isFutures(i)) return false;
      return isSportsCalendarToday(i);
    });
  }
  if (window === "next24h") {
    return live.filter((i) => {
      if (undatedInsightOrUser(i)) return true;
      if (isFutures(i)) return false;
      const h = hoursUntilStart(i);
      return h != null && h > 0 && h <= ROLLING_24H;
    });
  }
  if (window === "futures") {
    return live.filter((i) => {
      if (isFutures(i)) return true;
      const h = hoursUntilStart(i);
      return h != null && h > WEEK_HOURS;
    });
  }
  if (window === "month") {
    return live.filter((i) => {
      if (undatedInsightOrUser(i)) return true;
      if (isFutures(i)) return true;
      const h = hoursUntilStart(i);
      return h != null && h > 0 && h <= MONTH_HOURS;
    });
  }
  if (window === "week") {
    return live.filter((i) => {
      if (undatedInsightOrUser(i)) return true;
      if (isFutures(i)) return false;
      const h = hoursUntilStart(i);
      return h != null && h > 0 && h <= WEEK_HOURS;
    });
  }
  // soon (48h)
  return live.filter((i) => {
    if (undatedInsightOrUser(i)) return true;
    if (isFutures(i)) return false;
    const h = hoursUntilStart(i);
    return h != null && h > 0 && h <= NEAR_TERM_HOURS;
  });
}

/** After Scan/Repair, show a window that actually has picks — never hide a successful scan behind empty Today. */
export function pickWindowWithResults(
  items: SportsSignal[],
  preferred: SportsWindowKey = "today",
): SportsWindowKey {
  const order: SportsWindowKey[] = [preferred, "today", "next24h", "soon", "week", "all"];
  const seen = new Set<SportsWindowKey>();
  for (const key of order) {
    if (seen.has(key)) continue;
    seen.add(key);
    if (filterByWindow(items, key).length > 0) return key;
  }
  return preferred;
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
    case "player_props":
      return items.filter((i) => isPlayerPropPick(i));
    case "steam":
      return items.filter(
        (i) => (i.sharp_indicator ?? i.context?.sharp_indicator) === "steam",
      );
    case "value":
      return items.filter((i) => {
        const sharp = i.sharp_indicator ?? i.context?.sharp_indicator;
        return sharp === "value" || isOpenAiSportsPick(i);
      });
    case "openai":
      return items.filter((i) => isOpenAiSportsPick(i));
    case "my_bets":
      return items.filter((i) => isUserSportsPick(i));
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
        return getEdge(b) - getEdge(a) || compositeRank(b) - compositeRank(a);
      case "ev":
        return getEv(b) - getEv(a) || compositeRank(b) - compositeRank(a);
      case "confidence":
        return b.confidence_score - a.confidence_score || compositeRank(b) - compositeRank(a);
      case "risk_low":
        return a.risk_score - b.risk_score || compositeRank(b) - compositeRank(a);
      case "openai": {
        const ao = isOpenAiSportsPick(a) ? 1 : 0;
        const bo = isOpenAiSportsPick(b) ? 1 : 0;
        return bo - ao || compositeRank(b) - compositeRank(a);
      }
      case "player_props": {
        const ap = isPlayerPropPick(a) ? 1 : 0;
        const bp = isPlayerPropPick(b) ? 1 : 0;
        return bp - ap || compositeRank(b) - compositeRank(a);
      }
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
  const sourceKey = isUserSportsPick(row) ? "user" : isOpenAiSportsPick(row) ? "openai" : "odds";
  // Player props + user Search bets need selection in the key or sides collapse to one card.
  if (isPlayerPropPick(row) || isUserSportsPick(row)) {
    return `${eventId}|${betType}|${row.selection}|${sourceKey}`;
  }
  return `${eventId}|${betType}|${sourceKey}`;
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
