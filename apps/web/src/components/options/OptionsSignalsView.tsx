"use client";

import { useMemo, useState } from "react";
import { OptionSignalCard, type OptionSignal } from "@/components/options/OptionSignalCard";
import { SignalsToolbar } from "@/components/dashboard/SignalsToolbar";
import { filterSignals, sortSignals, type FilterKey, type SortKey } from "@/lib/signal-filters";
import type { SignalSummary } from "@/components/dashboard/OpportunityList";

function toSummary(row: OptionSignal): SignalSummary {
  const ctx = row.scoring_snapshot?.market_context as SignalSummary["context"] | undefined;
  const contractCost = row.premium * 100;
  return {
    id: row.id,
    module: "options",
    title: `${row.underlying} ${row.option_type.toUpperCase()} $${Number(row.strike).toFixed(0)}`,
    recommendation: row.recommendation,
    context: {
      ...ctx,
      profit_probability: row.scoring_snapshot?.profit_probability as number | undefined,
    },
    expiration: row.expiration,
    contract_cost: contractCost,
    is_budget: contractCost <= 100,
    premium: row.premium,
    scores: {
      confidence: row.confidence_score,
      risk: row.risk_score,
      opportunity: row.opportunity_score,
    },
  };
}

interface OptionsSignalsViewProps {
  allItems: OptionSignal[];
  budgetItems: OptionSignal[];
}

export function OptionsSignalsView({ allItems, budgetItems }: OptionsSignalsViewProps) {
  const [topSort, setTopSort] = useState<SortKey>("win_prob");
  const [topFilter, setTopFilter] = useState<FilterKey>("all");
  const [budgetSort, setBudgetSort] = useState<SortKey>("win_prob");
  const [budgetFilter, setBudgetFilter] = useState<FilterKey>("all");

  const topOrdered = useMemo(() => {
    const summaries = sortSignals(filterSignals(allItems.map(toSummary), topFilter), topSort);
    const byId = new Map(allItems.map((r) => [r.id, r]));
    return summaries.map((s) => byId.get(s.id)).filter(Boolean) as OptionSignal[];
  }, [allItems, topFilter, topSort]);

  const budgetOrdered = useMemo(() => {
    const summaries = sortSignals(filterSignals(budgetItems.map(toSummary), budgetFilter), budgetSort);
    const byId = new Map(budgetItems.map((r) => [r.id, r]));
    return summaries.map((s) => byId.get(s.id)).filter(Boolean) as OptionSignal[];
  }, [budgetItems, budgetFilter, budgetSort]);

  return (
    <div className="space-y-10">
      <section>
        <h2 className="mb-1 text-lg font-semibold">Top Picks</h2>
        <p className="mb-2 text-sm text-muted">Highest profit probability from the full market scan.</p>
        <SignalsToolbar
          sort={topSort}
          filter={topFilter}
          onSortChange={setTopSort}
          onFilterChange={setTopFilter}
          resultCount={topOrdered.length}
        />
        {topOrdered.length > 0 ? (
          <div className="space-y-6">
            {topOrdered.map((row, index) => (
              <OptionSignalCard key={row.id} row={row} rank={index + 1} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No picks match your filters.</p>
        )}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold">Under $100 Per Contract</h2>
        <p className="mb-2 text-sm text-muted">
          Same scoring criteria — options that cost $100 or less to open one contract.
        </p>
        <SignalsToolbar
          sort={budgetSort}
          filter={budgetFilter}
          onSortChange={setBudgetSort}
          onFilterChange={setBudgetFilter}
          resultCount={budgetOrdered.length}
        />
        {budgetOrdered.length > 0 ? (
          <div className="space-y-6">
            {budgetOrdered.map((row, index) => (
              <OptionSignalCard key={row.id} row={row} rank={index + 1} />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-surface/50 p-6 text-center text-sm text-muted">
            No budget picks match your filters.
          </div>
        )}
      </section>
    </div>
  );
}
