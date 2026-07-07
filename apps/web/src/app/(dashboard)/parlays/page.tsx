import { ParlaysView } from "@/components/parlays/ParlaysView";
import { PageHeader } from "@/components/ui/PageHeader";
import type { Parlay } from "@/components/parlays/ParlayCard";
import type { ParlayCategoryMeta } from "@/lib/parlay-categories";
import {
  emptyParlayCategoryCatalog,
  mergeParlayCategoryCatalog,
} from "@/lib/parlay-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface ParlaysListResponse {
  items: Parlay[];
}

interface CategoriesResponse {
  categories: ParlayCategoryMeta[];
}

export default async function ParlaysPage() {
  let items: Parlay[] = [];
  let categories = emptyParlayCategoryCatalog();

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      const [listResult, catResult] = await Promise.allSettled([
        apiFetch<ParlaysListResponse>("/parlays?limit=50", token),
        apiFetch<CategoriesResponse>("/parlays/categories", token),
      ]);

      if (listResult.status === "fulfilled") {
        items = listResult.value.items ?? [];
      }

      const apiCategories =
        catResult.status === "fulfilled" ? catResult.value.categories : undefined;
      categories = mergeParlayCategoryCatalog(apiCategories, items);
    }
  }

  return (
    <>
      <PageHeader
        title="Cross-Sport Parlays"
        description="Dozens of parlay options from your sports plays — conservative, balanced, and aggressive tiers in 24–48h and multi-day windows. Build after each sports scan for the latest lines."
      />
      <ParlaysView initialItems={items} initialCategories={categories} />
    </>
  );
}
