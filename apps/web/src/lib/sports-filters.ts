import type { SportsSignal } from "@/components/sports/SportsSignalCard";

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
export type SportsWindowKey = "today" | "soon" | "week" | "month" | "futures" | "all";

const NEAR_TERM_HOURS = 48;
const WEEK_HOURS = 168;
const MONTH_HOURS = 720;
const SPORTS_TZ = "America/New_York";

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

function getSoonest(row: SportsSignal): number {
  if (row.hours_until_start != null) return row.hours_until_start;
  // Undated OpenAI picks stay visible near the top of "soonest" rather than sinking to 9999.
  if (isOpenAiSportsPick(row)) return 20;
  return 9999;
}

function isFutures(row: SportsSignal): boolean {
  const bet = (row.bet_type || "").toLowerCase();
  return bet === "futures" || bet === "outright";
}

function easternDayKey(iso: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: SPORTS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(typeof iso === "string" ? new Date(iso) : iso);
}

/** Same Eastern calendar day as now — for Today parlays / sports window. */
export function isSportsCalendarToday(row: SportsSignal): boolean {
  if (!row.event_start || isFutures(row)) return false;
  const hours = row.hours_until_start ?? 9999;
  if (hours <= 0) return false;
  try {
    return easternDayKey(row.event_start) === easternDayKey(new Date());
  } catch {
    return false;
  }
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
  const todayBoost = isSportsCalendarToday(row) ? 4 : 0;
  const openaiBoost = isOpenAiSportsPick(row) ? 3 : 0;
  return opp + soonBoost + edge * 0.35 - latePenalty + todayBoost + openaiBoost;
}

export function filterByWindow(items: SportsSignal[], window: SportsWindowKey): SportsSignal[] {
  const started = items.filter((i) => (i.hours_until_start ?? 0) <= 0 && i.hours_until_start != null);
  // Mirror API: Atlas Insight + user-logged picks stay visible across date windows
  // (except futures-only), whether or not they have a kickoff time.
  const insightOrUser = (i: SportsSignal) => isOpenAiSportsPick(i) || isUserSportsPick(i);

  if (window === "all") {
    return items;
  }
  if (window === "today") {
    return items.filter((i) => isSportsCalendarToday(i) || insightOrUser(i));
  }
  if (window === "futures") {
    return items.filter(
      (i) => isFutures(i) || (i.hours_until_start ?? 0) > WEEK_HOURS || (insightOrUser(i) && isFutures(i)),
    );
  }
  if (window === "month") {
    const upcoming = items.filter((i) => {
      if (insightOrUser(i) && !isFutures(i)) return true;
      const h = i.hours_until_start ?? 9999;
      return (h > 0 && h <= MONTH_HOURS) || isFutures(i);
    });
    return [...started, ...upcoming];
  }
  if (window === "week") {
    const upcoming = items.filter((i) => {
      if (insightOrUser(i) && !isFutures(i)) return true;
      const h = i.hours_until_start ?? 9999;
      return h > 0 && h <= WEEK_HOURS;
    });
    return [...started, ...upcoming];
  }
  // soon (48h)
  const upcoming = items.filter((i) => {
    if (insightOrUser(i) && !isFutures(i)) return true;
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
  // Keep Odds, OpenAI, and user-logged picks side-by-side instead of deduping one away.
  const source = isUserSportsPick(row) ? "user" : isOpenAiSportsPick(row) ? "openai" : "odds";
  // Player props need selection in the key or every prop on a game collapses to one card.
  if (isPlayerPropPick(row)) {
    return `${eventId}|${betType}|${row.selection}|${source}`;
  }
  return `${eventId}|${betType}|${source}`;
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
