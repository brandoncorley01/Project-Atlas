import {
  PerformanceView,
  type PerformanceEntry,
  type PerformanceSummary,
} from "@/components/performance/PerformanceView";
import { PageHeader } from "@/components/ui/PageHeader";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface HistoryResponse {
  items: PerformanceEntry[];
}

export default async function PerformancePage() {
  let summary: PerformanceSummary = { days: 30 };
  let history: PerformanceEntry[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const [sumData, histData] = await Promise.all([
          apiFetch<PerformanceSummary>("/performance/summary?days=30", token),
          apiFetch<HistoryResponse>("/performance/history?limit=1000", token),
        ]);
        summary = sumData;
        history = histData.items;
      } catch {
        /* defaults */
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Performance & learning"
        description="Atlas learns from every graded result across sports, stocks, options, and parlays — then adapts the next picks. Your waiting list stays yours; Atlas board grades run in the background."
      />
      <PerformanceView initialSummary={summary} initialHistory={history} />
    </>
  );
}
