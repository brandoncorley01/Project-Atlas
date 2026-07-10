/** League display metadata for sports signals */
export interface SportMeta {
  label: string;
  emoji: string;
  accentClass: string;
}

const SPORT_LOOKUP: Record<string, SportMeta> = {
  basketball_nba: { label: "NBA", emoji: "🏀", accentClass: "bg-orange-500/20 text-orange-300" },
  basketball_ncaab: { label: "NCAAB", emoji: "🏀", accentClass: "bg-orange-500/20 text-orange-300" },
  basketball_wnba: { label: "WNBA", emoji: "🏀", accentClass: "bg-orange-500/20 text-orange-300" },
  basketball_wncaab: { label: "NCAAW", emoji: "🏀", accentClass: "bg-orange-500/20 text-orange-300" },
  americanfootball_nfl: { label: "NFL", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  americanfootball_nfl_preseason: { label: "NFL Preseason", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  americanfootball_ncaaf: { label: "NCAAF", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  americanfootball_cfl: { label: "CFL", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  baseball_mlb: { label: "MLB", emoji: "⚾", accentClass: "bg-red-500/20 text-red-300" },
  icehockey_nhl: { label: "NHL", emoji: "🏒", accentClass: "bg-sky-500/20 text-sky-300" },
  soccer_epl: { label: "EPL", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_usa_mls: { label: "MLS", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_spain_la_liga: { label: "La Liga", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_germany_bundesliga: { label: "Bundesliga", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_italy_serie_a: { label: "Serie A", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_france_ligue_one: { label: "Ligue 1", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_uefa_champs_league: { label: "UCL", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_uefa_europa_league: { label: "UEL", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_mexico_ligamx: { label: "Liga MX", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_brazil_campeonato: { label: "Brasileirão", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_fifa_world_cup: { label: "World Cup", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  mma_mixed_martial_arts: { label: "MMA", emoji: "🥊", accentClass: "bg-rose-500/20 text-rose-300" },
  boxing_boxing: { label: "Boxing", emoji: "🥊", accentClass: "bg-rose-500/20 text-rose-300" },
  tennis_atp: { label: "ATP", emoji: "🎾", accentClass: "bg-lime-500/20 text-lime-300" },
  tennis_wta: { label: "WTA", emoji: "🎾", accentClass: "bg-lime-500/20 text-lime-300" },
  golf_pga: { label: "PGA", emoji: "⛳", accentClass: "bg-lime-500/20 text-lime-300" },
  cricket_international_t20: { label: "T20 Cricket", emoji: "🏏", accentClass: "bg-amber-500/20 text-amber-300" },
  rugbyleague_nrl: { label: "NRL", emoji: "🏉", accentClass: "bg-teal-500/20 text-teal-300" },
  aussierules_afl: { label: "AFL", emoji: "🏉", accentClass: "bg-teal-500/20 text-teal-300" },
};

/** Display labels stored on signals → canonical lookup keys */
const LABEL_ALIASES: Record<string, string> = {
  nba: "basketball_nba",
  ncaab: "basketball_ncaab",
  wnba: "basketball_wnba",
  ncaaw: "basketball_wncaab",
  nfl: "americanfootball_nfl",
  "nfl_preseason": "americanfootball_nfl_preseason",
  ncaaf: "americanfootball_ncaaf",
  cfl: "americanfootball_cfl",
  mlb: "baseball_mlb",
  nhl: "icehockey_nhl",
  epl: "soccer_epl",
  mls: "soccer_usa_mls",
  "la_liga": "soccer_spain_la_liga",
  bundesliga: "soccer_germany_bundesliga",
  "serie_a": "soccer_italy_serie_a",
  "ligue_1": "soccer_france_ligue_one",
  ucl: "soccer_uefa_champs_league",
  uel: "soccer_uefa_europa_league",
  "liga_mx": "soccer_mexico_ligamx",
  brasileirão: "soccer_brazil_campeonato",
  brasileirao: "soccer_brazil_campeonato",
  "fifa_world_cup": "soccer_fifa_world_cup",
  "world_cup": "soccer_fifa_world_cup",
  mma: "mma_mixed_martial_arts",
  ufc: "mma_mixed_martial_arts",
  "ufc/mma": "mma_mixed_martial_arts",
  boxing: "boxing_boxing",
  tennis: "tennis_atp",
  atp: "tennis_atp",
  wta: "tennis_wta",
  pga: "golf_pga",
  "t20_cricket": "cricket_international_t20",
  nrl: "rugbyleague_nrl",
  afl: "aussierules_afl",
};

/** In-season tab order — summer (Apr–Sep) vs winter. Unknown leagues sort after. */
const SUMMER_TAB_PRIORITY = [
  "wnba",
  "mlb",
  "mls",
  "epl",
  "ucl",
  "la_liga",
  "bundesliga",
  "serie_a",
  "ligue_1",
  "liga_mx",
  "tennis",
  "atp",
  "wta",
  "mma",
  "boxing",
  "pga",
  "nfl_preseason",
  "ncaaf",
  "cfl",
  "t20_cricket",
  "nrl",
  "afl",
];

const WINTER_TAB_PRIORITY = [
  "nba",
  "nfl",
  "nhl",
  "ncaab",
  "ncaaf",
  "epl",
  "ucl",
  "la_liga",
  "bundesliga",
  "serie_a",
  "ligue_1",
  "mls",
  "mma",
  "boxing",
  "tennis",
  "atp",
  "wta",
  "mlb",
];

function normalizeSportKey(sport: string): string {
  return sport.toLowerCase().trim().replace(/\s+/g, "_");
}

function resolveLookupKey(sport: string): string {
  const key = normalizeSportKey(sport);
  if (SPORT_LOOKUP[key]) return key;
  if (LABEL_ALIASES[key]) return LABEL_ALIASES[key];
  // tennis_atp_wimbledon → tennis_atp; golf_pga_championship → golf_pga
  if (key.startsWith("tennis_atp")) return "tennis_atp";
  if (key.startsWith("tennis_wta")) return "tennis_wta";
  if (key.startsWith("golf_")) return "golf_pga";
  if (key.startsWith("soccer_") && !SPORT_LOOKUP[key]) {
    return key; // keep soccer_* for accent; label falls through
  }
  return key;
}

function tabPriorityRank(sport: string): number {
  const month = new Date().getUTCMonth() + 1; // 1–12
  const preferred = month >= 4 && month <= 9 ? SUMMER_TAB_PRIORITY : WINTER_TAB_PRIORITY;
  const key = normalizeSportKey(sport);
  const alias = LABEL_ALIASES[key] ? normalizeSportKey(SPORT_LOOKUP[LABEL_ALIASES[key]]?.label ?? key) : key;
  const labelKey = normalizeSportKey(getSportMeta(sport).label);
  const idx = preferred.findIndex(
    (p) => p === key || p === alias || p === labelKey || key.includes(p) || labelKey.includes(p),
  );
  return idx === -1 ? 500 : idx;
}

export function getSportMeta(sport: string): SportMeta {
  const lookup = resolveLookupKey(sport);
  if (SPORT_LOOKUP[lookup]) return SPORT_LOOKUP[lookup];
  if (lookup.startsWith("tennis_")) {
    return { label: sport.replace(/_/g, " ").slice(0, 18), emoji: "🎾", accentClass: "bg-lime-500/20 text-lime-300" };
  }
  if (lookup.startsWith("soccer_")) {
    const short = sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return { label: short.slice(0, 14), emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" };
  }
  if (lookup.startsWith("golf_")) {
    return { label: "Golf", emoji: "⛳", accentClass: "bg-lime-500/20 text-lime-300" };
  }
  if (lookup.startsWith("cricket_")) {
    return { label: "Cricket", emoji: "🏏", accentClass: "bg-amber-500/20 text-amber-300" };
  }
  const short = sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { label: short.slice(0, 14), emoji: "🏟️", accentClass: "bg-violet-500/20 text-violet-300" };
}

export function buildSportCounts(items: Array<{ sport: string }>): { sport: string; count: number; meta: SportMeta }[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = normalizeSportKey(item.sport);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([sport, count]) => ({ sport, count, meta: getSportMeta(sport) }))
    .sort((a, b) => {
      const rankDiff = tabPriorityRank(a.sport) - tabPriorityRank(b.sport);
      if (rankDiff !== 0) return rankDiff;
      return b.count - a.count;
    });
}

/**
 * Full league catalog always available in the UI, sorted by seasonal relevance.
 * Merges live pick counts with the seasonal catalog so empty leagues still appear.
 */
export function buildLeagueCatalog(
  items: Array<{ sport: string }>,
  extraLeagues: string[] = [],
): { sport: string; count: number; meta: SportMeta }[] {
  const month = new Date().getUTCMonth() + 1;
  const seasonal = month >= 4 && month <= 9 ? SUMMER_CATALOG : WINTER_CATALOG;
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = normalizeSportKey(item.sport);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const seen = new Set<string>();
  const rows: { sport: string; count: number; meta: SportMeta }[] = [];

  const pushLabel = (label: string) => {
    const key = normalizeSportKey(label);
    if (seen.has(key)) return;
    seen.add(key);
    // Match pick counts by label or alias
    let count = counts.get(key) ?? 0;
    if (count === 0) {
      for (const [ck, cv] of counts) {
        if (ck === key || ck.includes(key) || key.includes(ck)) {
          count = cv;
          break;
        }
      }
    }
    rows.push({ sport: key, count, meta: getSportMeta(label) });
  };

  for (const label of seasonal) pushLabel(label);
  for (const label of extraLeagues) pushLabel(label);
  // Any live sports not already in the catalog (e.g. rotating tennis events)
  for (const [key, count] of counts) {
    if (!seen.has(key)) {
      seen.add(key);
      rows.push({ sport: key, count, meta: getSportMeta(key) });
    }
  }

  return rows.sort((a, b) => {
    const rankDiff = tabPriorityRank(a.sport) - tabPriorityRank(b.sport);
    if (rankDiff !== 0) return rankDiff;
    return b.count - a.count;
  });
}

/** Leagues commonly scanned — shown as hints when empty */
export const FEATURED_LEAGUES = [
  "WNBA",
  "MLB",
  "MLS",
  "EPL",
  "Tennis",
  "MMA",
  "Boxing",
  "La Liga",
  "NFL",
  "NBA",
  "NHL",
  "NCAAF",
];

/** Always-visible summer catalog (Apr–Sep) */
const SUMMER_CATALOG = [
  "WNBA",
  "MLB",
  "MLS",
  "EPL",
  "UCL",
  "La Liga",
  "Bundesliga",
  "Serie A",
  "Ligue 1",
  "Liga MX",
  "Tennis",
  "MMA",
  "Boxing",
  "PGA",
  "NFL Preseason",
  "NCAAF",
  "CFL",
  "T20 Cricket",
  "NRL",
  "AFL",
  "World Cup",
  "NBA",
  "NHL",
  "NFL",
];

/** Always-visible winter catalog (Oct–Mar) */
const WINTER_CATALOG = [
  "NBA",
  "NFL",
  "NHL",
  "NCAAB",
  "NCAAF",
  "EPL",
  "UCL",
  "La Liga",
  "Bundesliga",
  "Serie A",
  "Ligue 1",
  "MLS",
  "MMA",
  "Boxing",
  "Tennis",
  "PGA",
  "MLB",
  "WNBA",
  "NCAAW",
  "CFL",
];
