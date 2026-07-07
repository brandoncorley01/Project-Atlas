import { StocksSignalsView } from "@/components/stocks/StocksSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";
import type { StockSignal } from "@/components/stocks/StockSignalCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface StocksListResponse {
  items: StockSignal[];
}

export default async function StocksPage() {
  let items: StockSignal[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const data = await apiFetch<StocksListResponse>("/signals/stocks?limit=20", token);
        items = data.items;
      } catch {
        items = [];
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Stock Swing Trading"
        description="2–7 day and 1–2 week setups ranked by opportunity score. Each card shows entry zone, stop loss, and price targets — tap for the full chart."
      />
      <StocksSignalsView initialItems={items} />
    </>
  );
}
