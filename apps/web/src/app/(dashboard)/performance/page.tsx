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

function emptySummary(days = 30): PerformanceSummary {
  return { days };
}

export default async function PerformancePage() {
  let summary: PerformanceSummary = emptySummary();
  let history: PerformanceEntry[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      // Load independently — a summary recursion/timeout must not wipe history.
      const [sumResult, histResult] = await Promise.allSettled([
        apiFetch<PerformanceSummary>("/performance/summary?days=30", token),
        apiFetch<HistoryResponse>("/performance/history?limit=1000", token),
      ]);

      if (histResult.status === "fulfilled") {
        history = histResult.value.items ?? [];
      }
      if (sumResult.status === "fulfilled") {
        summary = sumResult.value;
      } else if (history.length > 0) {
        // Lightweight leaf summary from SSR history so metrics aren't blank.
        const closed = history.filter((r) =>
          ["win", "loss", "scratch"].includes(r.outcome),
        );
        const wins = closed.filter((r) => r.outcome === "win");
        const losses = closed.filter((r) => r.outcome === "loss");
        const decided = wins.length + losses.length;
        summary = {
          days: 30,
          total_signals: closed.length,
          wins: wins.length,
          losses: losses.length,
          scratches: closed.filter((r) => r.outcome === "scratch").length,
          pending: history.filter((r) => r.outcome === "pending").length,
          win_rate:
            decided > 0 ? Math.round((wins.length / decided) * 1000) / 10 : null,
        };
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Performance & learning"
        description="Atlas learns from every graded result across sports, stocks, options, and parlays — then adapts the next picks. Tap Edit or Change result to correct any option or parlay outcome."
      />
      <PerformanceView initialSummary={summary} initialHistory={history} />
    </>
  );
}
