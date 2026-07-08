import { StocksSignalsView } from "@/components/stocks/StocksSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";
import type { StockSignal } from "@/components/stocks/StockSignalCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface StocksListResponse {
  items: StockSignal[];
}

export default async function StocksPage({
  searchParams,
}: {
  searchParams: Promise<{ ticker?: string }>;
}) {
  const params = await searchParams;
  const initialTicker = params.ticker?.toUpperCase();
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
        description="Type any ticker for a full analysis with chart, entry zone, stop-loss, and take-profit targets — or scan the market for ranked swing setups."
      />
      <StocksSignalsView initialItems={items} initialTicker={initialTicker} />
    </>
  );
}
