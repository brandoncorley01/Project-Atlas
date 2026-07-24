import { Suspense } from "react";
import { OptionsIntelligenceView } from "@/components/market-intelligence/OptionsIntelligenceView";

export default function OptionsIntelligencePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading Options Intelligence…</p>}>
      <OptionsIntelligenceView />
    </Suspense>
  );
}
