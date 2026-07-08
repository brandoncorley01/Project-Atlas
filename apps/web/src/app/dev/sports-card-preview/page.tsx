"use client";

import { SportsSignalCard } from "@/components/sports/SportsSignalCard";
import { MOBILE_LAYOUT_PREVIEW_SIGNAL } from "@/lib/sports-mock-preview";

export default function SportsCardPreviewPage() {
  return (
    <div className="mx-auto w-full min-w-0 max-w-7xl px-4 py-6" data-testid="sports-card-preview">
      <p className="mb-4 text-xs text-muted">
        Dev preview — mock data only, no sports scan.
      </p>
      <SportsSignalCard
        row={MOBILE_LAYOUT_PREVIEW_SIGNAL}
        rank={1}
        parlaySelected={false}
        onParlayToggle={() => {}}
      />
    </div>
  );
}
