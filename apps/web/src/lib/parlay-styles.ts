export type ParlayStyle = "conservative" | "balanced" | "aggressive";

export interface ParlayStyleMeta {
  slug: ParlayStyle;
  title: string;
  short_label: string;
  description: string;
  leg_count: number;
  count: number;
}

export const PARLAY_STYLE_DEFINITIONS: Omit<ParlayStyleMeta, "count">[] = [
  {
    slug: "conservative",
    title: "Conservative",
    short_label: "Conservative",
    description: "2-leg tickets — highest hit rate, smaller but faster payouts.",
    leg_count: 2,
  },
  {
    slug: "balanced",
    title: "Balanced",
    short_label: "Balanced",
    description: "3-leg tickets — blend of edge and payout multiplier.",
    leg_count: 3,
  },
  {
    slug: "aggressive",
    title: "Aggressive",
    short_label: "Aggressive",
    description: "4-leg tickets — max odds for turning small stakes into large returns.",
    leg_count: 4,
  },
];

export function buildParlayStyleCatalog(
  items: Array<{ style?: string | null }>,
): ParlayStyleMeta[] {
  const counts: Record<string, number> = {};
  for (const def of PARLAY_STYLE_DEFINITIONS) {
    counts[def.slug] = 0;
  }
  for (const item of items) {
    const slug = item.style;
    if (slug && slug in counts) counts[slug] += 1;
  }
  return PARLAY_STYLE_DEFINITIONS.map((def) => ({
    ...def,
    count: counts[def.slug] ?? 0,
  }));
}

export function emptyParlayStyleCatalog(): ParlayStyleMeta[] {
  return PARLAY_STYLE_DEFINITIONS.map((def) => ({ ...def, count: 0 }));
}

export const PARLAY_STYLE_LABELS: Record<string, string> = {
  conservative: "Conservative",
  balanced: "Balanced",
  aggressive: "Aggressive",
};
