import { SportsSignalsView } from "@/components/sports/SportsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";
import type { SportsSignal } from "@/components/sports/SportsSignalCard";
import type { SportsCategoryMeta } from "@/lib/sports-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

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
          apiFetch<SportsListResponse>("/signals/sports?limit=50&window=week", token),
          apiFetch<CategoriesResponse>("/signals/sports/categories", token),
        ]);
        items = listData.items;
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
            24/7 GLOBAL
          </span>
        }
        description="Your scan results stay on this page until the next successful scan — rescore uses 0 credits when cache is warm; Fetch live odds spends API credits."
      />
      <SportsSignalsView initialItems={items} initialCategories={categories} />
    </>
  );
}
