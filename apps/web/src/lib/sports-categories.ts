export interface SportsCategoryMeta {
  slug: string;
  title: string;
  short_label: string;
  description: string;
  guide: string;
  count: number;
}

export const CATEGORY_SLUG_LABELS: Record<string, string> = {
  starting_soon: "Live Soon",
  top_picks: "Top Picks",
  best_edge: "Best Edge",
  highest_ev: "Highest EV",
  most_likely: "Most Likely",
  greatest_odds: "Longshots",
  steam_moves: "Steam",
  value_plays: "Value",
  safest_plays: "Safest",
};
