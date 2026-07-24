import { Suspense } from "react";
import { MarketIntelligenceView } from "@/components/market-intelligence/MarketIntelligenceView";

export default function MarketIntelligencePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading Market Intelligence…</p>}>
      <MarketIntelligenceView />
    </Suspense>
  );
}
