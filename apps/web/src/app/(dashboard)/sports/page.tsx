import { SportsSignalsView } from "@/components/sports/SportsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import type { SportsCategoryMeta } from "@/lib/sports-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";
import { enrichSportsItemsWithKalshi } from "@/lib/kalshi-public-pulse";

interface SportsListResponse {
  items: SportsSignal[];
}

interface CategoriesResponse {
  categories: SportsCategoryMeta[];
}

export default async function SportsPage() {
  let items: SportsSignal[] = [];
  let categories: SportsCategoryMeta[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const [listData, catData] = await Promise.all([
          apiFetch<SportsListResponse>("/signals/sports?limit=200&window=all", token),
          apiFetch<CategoriesResponse>("/signals/sports/categories", token),
        ]);
        items = (await enrichSportsItemsWithKalshi(
          (listData.items ?? []) as unknown as Record<string, unknown>[],
          { maxRows: 48 },
        )) as unknown as SportsSignal[];
        categories = catData.categories;
      } catch {
        items = [];
        categories = [];
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Sports Betting"
        badge={
          <span className="rounded-full bg-violet-600 px-2.5 py-0.5 text-xs font-bold text-white">
            ONE SIDE / MARKET
          </span>
        }
        description="Picks stay on your board until you Scan or Rescore. Search events like FanDuel, log your own bets, or use Scan / Fetch / Rescore / Atlas Insight."
      />
      <SportsSignalsView initialItems={items} initialCategories={categories} />
    </>
  );
}
