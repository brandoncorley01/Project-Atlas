export interface ParlayCategoryMeta {
  slug: string;
  title: string;
  short_label: string;
  description: string;
  guide: string;
  count: number;
}

/** Static catalog — tabs always render even if the categories API is unavailable. */
export const PARLAY_CATEGORY_DEFINITIONS: Omit<ParlayCategoryMeta, "count">[] = [
  {
    slug: "today",
    title: "Today",
    short_label: "Today",
    description:
      "Every leg kicks off today (US/Eastern) — same-day slate only.",
    guide:
      "Same-day parlays: all legs start on today's Eastern calendar date. " +
      "Atlas builds up to six options per risk tier from today's sports picks only.",
  },
  {
    slug: "next_48h",
    title: "Next 24–48 Hours",
    short_label: "24–48h",
    description:
      "All legs kick off within the next 48 hours, spanning more than today.",
    guide:
      "Quick-turn parlays: every leg starts within 48 hours but not all on the same day. " +
      "Atlas builds up to six options per risk tier ranked by edge, payout, and sport diversity.",
  },
  {
    slug: "multi_day",
    title: "Multi-Day Stretch",
    short_label: "Multi-day",
    description:
      "Legs span more than 48 hours — the ticket plays out over several days.",
    guide:
      "Multi-day parlays combine games separated by more than 48 hours. " +
      "Higher calendar risk: news, injuries, and line moves can hit before later legs. " +
      "Only upcoming games are included — finished legs are removed automatically.",
  },
];

export const PARLAY_CATEGORY_LABELS: Record<string, string> = {
  today: "Today",
  next_48h: "24–48h",
  multi_day: "Multi-day",
};

export function emptyParlayCategoryCatalog(): ParlayCategoryMeta[] {
  return PARLAY_CATEGORY_DEFINITIONS.map((def) => ({ ...def, count: 0 }));
}

export function buildParlayCategoryCatalog(
  items: Array<{ categories?: string[] | null }>,
): ParlayCategoryMeta[] {
  const counts: Record<string, number> = {};
  for (const def of PARLAY_CATEGORY_DEFINITIONS) {
    counts[def.slug] = 0;
  }
  for (const item of items) {
    for (const slug of item.categories ?? []) {
      if (slug in counts) counts[slug] += 1;
    }
  }
  return PARLAY_CATEGORY_DEFINITIONS.map((def) => ({
    ...def,
    count: counts[def.slug] ?? 0,
  }));
}

export function mergeParlayCategoryCatalog(
  apiCategories: ParlayCategoryMeta[] | undefined,
  items: Array<{ categories?: string[] | null }>,
): ParlayCategoryMeta[] {
  const fromItems = buildParlayCategoryCatalog(items);
  if (!apiCategories?.length) return fromItems;

  const apiBySlug = new Map(apiCategories.map((c) => [c.slug, c]));
  return PARLAY_CATEGORY_DEFINITIONS.map((def) => {
    const fromApi = apiBySlug.get(def.slug);
    const fromList = fromItems.find((c) => c.slug === def.slug);
    return {
      ...def,
      count: Math.max(fromApi?.count ?? 0, fromList?.count ?? 0),
    };
  });
}
