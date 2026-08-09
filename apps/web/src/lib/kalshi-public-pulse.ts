/**
 * Kalshi public-probability pulse (server-side).
 * Used by the Atlas BFF so sports cards get the indicator even when the
 * Render API has not been redeployed with Kalshi enrichment yet.
 */

export type KalshiPublicSide = {
  abbr: string;
  label: string;
  implied_pct: number;
  market_ticker?: string | null;
};

export type KalshiPublicMarket = {
  source: "kalshi";
  series_ticker: string;
  event_ticker: string;
  title: string;
  as_of: string;
  url: string | null;
  side_a: KalshiPublicSide;
  side_b: KalshiPublicSide;
  history_a: number[];
  history_b: number[];
  stance_vs_pick: "sure" | "mixed" | "doubtful" | null;
};

const KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2";

const SPORT_KEY_TO_SERIES: Record<string, string> = {
  baseball_mlb: "KXMLBGAME",
  baseball_mlb_preseason: "KXMLBSTGAME",
  americanfootball_nfl: "KXNFLGAME",
  americanfootball_nfl_preseason: "KXNFLGAME",
  basketball_nba: "KXNBAGAME",
  basketball_wnba: "KXWNBAGAME",
  icehockey_nhl: "KXNHLGAME",
  soccer_epl: "KXEPLGAME",
  soccer_usa_mls: "KXMLSGAME",
  soccer_spain_la_liga: "KXLALIGAGAME",
  soccer_germany_bundesliga: "KXBUNDESLIGAGAME",
  soccer_italy_serie_a: "KXSERIEAGAME",
  soccer_france_ligue_one: "KXLIGUE1GAME",
  americanfootball_ncaaf: "KXNCAAFGAME",
  basketball_ncaab: "KXNCAABGAME",
  mma_mixed_martial_arts: "KXUFCFIGHT",
  boxing_boxing: "KXBOXINGFIGHT",
  tennis_atp_french_open: "KXATPMATCH",
  tennis_wta_french_open: "KXWTAMATCH",
  tennis_atp_wimbledon: "KXATPMATCH",
  tennis_wta_wimbledon: "KXWTAMATCH",
  tennis_atp_us_open: "KXATPMATCH",
  tennis_wta_us_open: "KXWTAMATCH",
};

const SPORT_LABEL_TO_SERIES: Record<string, string> = {
  mlb: "KXMLBGAME",
  baseball: "KXMLBGAME",
  nfl: "KXNFLGAME",
  football: "KXNFLGAME",
  nba: "KXNBAGAME",
  basketball: "KXNBAGAME",
  wnba: "KXWNBAGAME",
  nhl: "KXNHLGAME",
  hockey: "KXNHLGAME",
  epl: "KXEPLGAME",
  mls: "KXMLSGAME",
  la_liga: "KXLALIGAGAME",
  laliga: "KXLALIGAGAME",
  bundesliga: "KXBUNDESLIGAGAME",
  serie_a: "KXSERIEAGAME",
  ligue_1: "KXLIGUE1GAME",
  ligue1: "KXLIGUE1GAME",
  ncaaf: "KXNCAAFGAME",
  ncaab: "KXNCAABGAME",
  mma: "KXUFCFIGHT",
  ufc: "KXUFCFIGHT",
  boxing: "KXBOXINGFIGHT",
  atp: "KXATPMATCH",
  wta: "KXWTAMATCH",
  tennis: "KXATPMATCH",
};

const STOP = new Set([
  "the",
  "fc",
  "cf",
  "sc",
  "ac",
  "afc",
  "club",
  "city",
  "town",
  "united",
  "athletic",
]);

type CacheEntry<T> = { at: number; value: T };
const eventsCache = new Map<string, CacheEntry<KalshiEvent[]>>();
const EVENTS_TTL_MS = 10 * 60 * 1000;

type KalshiMarket = {
  ticker?: string;
  title?: string;
  yes_sub_title?: string;
  last_price_dollars?: string | number;
  yes_bid_dollars?: string | number;
  previous_yes_bid_dollars?: string | number;
  last_price?: string | number;
  yes_bid?: string | number;
};

type KalshiEvent = {
  event_ticker?: string;
  title?: string;
  markets?: KalshiMarket[];
};

function tokens(name: string): Set<string> {
  const raw = (name || "").toLowerCase().match(/[a-z0-9]+/g) || [];
  const out = new Set<string>();
  for (const t of raw) {
    if (t.length < 2 || STOP.has(t)) continue;
    out.add(t);
    if (t.endsWith("s") && t.length > 3) out.add(t.slice(0, -1));
  }
  return out;
}

function abbr(name: string): string {
  const text = (name || "").trim();
  if (!text) return "??";
  if (/^[A-Z]{2,4}$/.test(text)) return text;
  const parts = text.split(/\s+/).filter((p) => p && !STOP.has(p.toLowerCase()));
  if (!parts.length) return text.slice(0, 3).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 3).toUpperCase();
  return parts
    .map((p) => p[0])
    .join("")
    .slice(0, 4)
    .toUpperCase();
}

function dollarsToPct(value: unknown): number | null {
  if (value == null) return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  const pct = n > 1.5 ? n : n * 100;
  return Math.max(0, Math.min(100, Math.round(pct * 10) / 10));
}

function teamScore(atlasName: string, kalshiName: string): number {
  const a = tokens(atlasName);
  const b = tokens(kalshiName);
  if (!a.size || !b.size) return 0;
  if ([...a].every((t) => b.has(t)) && a.size === b.size) return 1;
  const inter = [...a].filter((t) => b.has(t));
  const al = atlasName.toLowerCase().trim();
  const kl = kalshiName.toLowerCase().trim();
  if (!inter.length) {
    if (al && kl && (al.includes(kl) || kl.includes(al))) return 0.72;
    return 0;
  }
  const shorter = Math.min(a.size, b.size);
  const coverage = inter.length / Math.max(shorter, 1);
  const union = new Set([...a, ...b]).size;
  const jaccard = inter.length / Math.max(union, 1);
  let score = Math.max(coverage, jaccard);
  const subset =
    [...b].every((t) => a.has(t)) || [...a].every((t) => b.has(t));
  if (subset) score = Math.max(score, 0.85);
  if (al && kl && (al.includes(kl) || kl.includes(al))) score = Math.max(score, 0.72);
  return score;
}

export function seriesForSport(sportKey?: string | null, sport?: string | null): string | null {
  const key = (sportKey || "").trim().toLowerCase();
  if (key && SPORT_KEY_TO_SERIES[key]) return SPORT_KEY_TO_SERIES[key];
  const label = (sport || "").trim().toLowerCase().replace(/\s+/g, "_");
  if (label && SPORT_KEY_TO_SERIES[label]) return SPORT_KEY_TO_SERIES[label];
  for (const [token, series] of Object.entries(SPORT_LABEL_TO_SERIES)) {
    if (token === label || label.split("_").includes(token) || key.split("_").includes(token)) {
      return series;
    }
    if ((sport || "").toLowerCase().includes(token)) return series;
  }
  return null;
}

function marketImplied(m: KalshiMarket): number | null {
  for (const key of [
    "last_price_dollars",
    "yes_bid_dollars",
    "previous_yes_bid_dollars",
    "last_price",
    "yes_bid",
  ] as const) {
    const pct = dollarsToPct(m[key]);
    if (pct != null) return pct;
  }
  return null;
}

function matchEvent(
  events: KalshiEvent[],
  homeTeam: string,
  awayTeam: string,
): { event: KalshiEvent; marketA: KalshiMarket; marketB: KalshiMarket } | null {
  let best: { event: KalshiEvent; marketA: KalshiMarket; marketB: KalshiMarket; score: number } | null =
    null;
  for (const event of events) {
    const markets = (event.markets || []).filter(Boolean);
    if (markets.length < 2) continue;
    const sides = markets.slice(0, 6);
    for (let i = 0; i < sides.length; i += 1) {
      for (let j = i + 1; j < sides.length; j += 1) {
        const mA = sides[i];
        const mB = sides[j];
        const nameA = String(mA.yes_sub_title || mA.title || "");
        const nameB = String(mB.yes_sub_title || mB.title || "");
        const s1 = teamScore(awayTeam, nameA) + teamScore(homeTeam, nameB);
        const s2 = teamScore(awayTeam, nameB) + teamScore(homeTeam, nameA);
        const score = Math.max(s1, s2);
        if (!best || score > best.score) {
          best = {
            event,
            score,
            marketA: s1 >= s2 ? mA : mB,
            marketB: s1 >= s2 ? mB : mA,
          };
        }
      }
    }
  }
  if (!best || best.score < 1.1) return null;
  return best;
}

function stanceVsPick(
  selection: string | undefined,
  nameA: string,
  nameB: string,
  pctA: number,
  pctB: number,
): "sure" | "mixed" | "doubtful" | null {
  if (!selection) return null;
  let scoreA = teamScore(selection, nameA);
  let scoreB = teamScore(selection, nameB);
  if (scoreA < 0.35 && scoreB < 0.35) {
    const sel = tokens(selection);
    if (!sel.size) return null;
    scoreA = [...sel].filter((t) => tokens(nameA).has(t)).length / sel.size;
    scoreB = [...sel].filter((t) => tokens(nameB).has(t)).length / sel.size;
  }
  if (scoreA < 0.2 && scoreB < 0.2) return null;
  const pickPct = scoreA >= scoreB ? pctA : pctB;
  if (pickPct >= 58) return "sure";
  if (pickPct <= 42) return "doubtful";
  return "mixed";
}

async function fetchSeriesEvents(seriesTicker: string): Promise<KalshiEvent[]> {
  const cached = eventsCache.get(seriesTicker);
  if (cached && Date.now() - cached.at < EVENTS_TTL_MS) return cached.value;

  const url = new URL(`${KALSHI_API_BASE}/events`);
  url.searchParams.set("limit", "200");
  url.searchParams.set("status", "open");
  url.searchParams.set("series_ticker", seriesTicker);
  url.searchParams.set("with_nested_markets", "true");

  const res = await fetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Kalshi events ${res.status}`);
  const payload = (await res.json()) as { events?: KalshiEvent[] };
  const events = (payload.events || []).filter(Boolean);
  eventsCache.set(seriesTicker, { at: Date.now(), value: events });
  return events;
}

function participantsFromRow(row: Record<string, unknown>): { home: string; away: string } {
  const snap =
    row.scoring_snapshot && typeof row.scoring_snapshot === "object"
      ? (row.scoring_snapshot as Record<string, unknown>)
      : {};
  let home = String(snap.home_team || "").trim();
  let away = String(snap.away_team || "").trim();
  if (home && away) return { home, away };

  const event = String(row.event_name || "");
  if (event.includes(" @ ")) {
    const [a, h] = event.split(" @ ");
    return { home: (h || "").trim(), away: (a || "").trim() };
  }
  const vs = event.split(/\s+vs\.?\s+/i);
  if (vs.length === 2) return { home: vs[0].trim(), away: vs[1].trim() };
  return { home, away };
}

function sportKeyFromRow(row: Record<string, unknown>): string | null {
  const snap =
    row.scoring_snapshot && typeof row.scoring_snapshot === "object"
      ? (row.scoring_snapshot as Record<string, unknown>)
      : {};
  const lm =
    row.line_movement && typeof row.line_movement === "object"
      ? (row.line_movement as Record<string, unknown>)
      : {};
  const key = snap.sport_key || lm.sport_key;
  return key ? String(key) : null;
}

function buildPulse(
  event: KalshiEvent,
  marketA: KalshiMarket,
  marketB: KalshiMarket,
  seriesTicker: string,
  selection?: string,
): KalshiPublicMarket | null {
  const nameA = String(marketA.yes_sub_title || marketA.title || "Side A");
  const nameB = String(marketB.yes_sub_title || marketB.title || "Side B");
  let pctA = marketImplied(marketA);
  let pctB = marketImplied(marketB);
  if (pctA == null && pctB != null) pctA = Math.round((100 - pctB) * 10) / 10;
  if (pctB == null && pctA != null) pctB = Math.round((100 - pctA) * 10) / 10;
  if (pctA == null || pctB == null) return null;
  const total = pctA + pctB;
  if (total > 0) {
    pctA = Math.round((pctA * 1000) / total) / 10;
    pctB = Math.round((100 - pctA) * 10) / 10;
  }
  const eventTicker = String(event.event_ticker || "");
  return {
    source: "kalshi",
    series_ticker: seriesTicker,
    event_ticker: eventTicker,
    title: String(event.title || ""),
    as_of: new Date().toISOString(),
    url: eventTicker ? `https://kalshi.com/markets/${eventTicker.toLowerCase()}` : null,
    side_a: {
      abbr: abbr(nameA),
      label: nameA,
      implied_pct: pctA,
      market_ticker: marketA.ticker || null,
    },
    side_b: {
      abbr: abbr(nameB),
      label: nameB,
      implied_pct: pctB,
      market_ticker: marketB.ticker || null,
    },
    // Current print only — keeps BFF enrichment fast on list loads.
    history_a: [pctA],
    history_b: [pctB],
    stance_vs_pick: stanceVsPick(selection, nameA, nameB, pctA, pctB),
  };
}

export async function enrichSportsItemsWithKalshi<T extends Record<string, unknown>>(
  items: T[],
  options?: { maxRows?: number },
): Promise<T[]> {
  const maxRows = options?.maxRows ?? 40;
  if (!items.length) return items;

  const targets = items.slice(0, maxRows);
  const seriesNeeded = new Set<string>();
  for (const row of targets) {
    const series = seriesForSport(sportKeyFromRow(row), String(row.sport || ""));
    if (series) seriesNeeded.add(series);
  }

  await Promise.allSettled([...seriesNeeded].map((s) => fetchSeriesEvents(s)));

  await Promise.allSettled(
    targets.map(async (row) => {
      if (row.public_market && typeof row.public_market === "object") return;
      const snap =
        row.scoring_snapshot && typeof row.scoring_snapshot === "object"
          ? (row.scoring_snapshot as Record<string, unknown>)
          : null;
      if (snap?.public_market && typeof snap.public_market === "object") {
        (row as Record<string, unknown>).public_market = snap.public_market;
        return;
      }
      const { home, away } = participantsFromRow(row);
      if (!home || !away) return;
      const series = seriesForSport(sportKeyFromRow(row), String(row.sport || ""));
      if (!series) return;
      try {
        const events = await fetchSeriesEvents(series);
        const matched = matchEvent(events, home, away);
        if (!matched) return;
        const pulse = buildPulse(
          matched.event,
          matched.marketA,
          matched.marketB,
          series,
          String(row.selection || ""),
        );
        if (pulse) (row as Record<string, unknown>).public_market = pulse;
      } catch {
        /* non-fatal */
      }
    }),
  );

  return items;
}
