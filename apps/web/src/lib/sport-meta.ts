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
  americanfootball_nfl: { label: "NFL", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  americanfootball_ncaaf: { label: "NCAAF", emoji: "🏈", accentClass: "bg-emerald-500/20 text-emerald-300" },
  baseball_mlb: { label: "MLB", emoji: "⚾", accentClass: "bg-red-500/20 text-red-300" },
  icehockey_nhl: { label: "NHL", emoji: "🏒", accentClass: "bg-sky-500/20 text-sky-300" },
  soccer_epl: { label: "EPL", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_usa_mls: { label: "MLS", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_spain_la_liga: { label: "La Liga", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_germany_bundesliga: { label: "Bundesliga", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_italy_serie_a: { label: "Serie A", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_france_ligue_one: { label: "Ligue 1", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  soccer_uefa_champs_league: { label: "UCL", emoji: "⚽", accentClass: "bg-violet-500/20 text-violet-300" },
  mma_mixed_martial_arts: { label: "MMA", emoji: "🥊", accentClass: "bg-rose-500/20 text-rose-300" },
  boxing_boxing: { label: "Boxing", emoji: "🥊", accentClass: "bg-rose-500/20 text-rose-300" },
  tennis_atp: { label: "Tennis", emoji: "🎾", accentClass: "bg-lime-500/20 text-lime-300" },
  golf_pga: { label: "PGA", emoji: "⛳", accentClass: "bg-lime-500/20 text-lime-300" },
};

function normalizeSportKey(sport: string): string {
  return sport.toLowerCase().trim().replace(/\s+/g, "_");
}

export function getSportMeta(sport: string): SportMeta {
  const key = normalizeSportKey(sport);
  if (SPORT_LOOKUP[key]) return SPORT_LOOKUP[key];
  const short = sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { label: short.slice(0, 12), emoji: "🏟️", accentClass: "bg-violet-500/20 text-violet-300" };
}

export function buildSportCounts(items: Array<{ sport: string }>): { sport: string; count: number; meta: SportMeta }[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = normalizeSportKey(item.sport);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([sport, count]) => ({ sport, count, meta: getSportMeta(sport) }))
    .sort((a, b) => b.count - a.count);
}

/** Leagues commonly scanned — shown as hints when empty */
export const FEATURED_LEAGUES = [
  "NBA", "NFL", "MLB", "NHL", "EPL", "MLS", "NCAAB", "NCAAF", "UFC/MMA", "Tennis",
];
