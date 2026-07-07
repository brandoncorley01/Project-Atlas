"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { OpportunityList, type SignalSummary } from "@/components/dashboard/OpportunityList";
import { SignalsToolbar } from "@/components/dashboard/SignalsToolbar";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { filterSignals, sortSignals, type FilterKey, type SortKey } from "@/lib/signal-filters";

interface DashboardSignalsProps {
  topOpportunities: SignalSummary[];
  budgetOpportunities: SignalSummary[];
  stockOpportunities: SignalSummary[];
  sportsOpportunities: SignalSummary[];
}

export function DashboardSignals({
  topOpportunities,
  budgetOpportunities,
  stockOpportunities,
  sportsOpportunities,
}: DashboardSignalsProps) {
  const [topSort, setTopSort] = useState<SortKey>("win_prob");
  const [topFilter, setTopFilter] = useState<FilterKey>("all");
  const [budgetSort, setBudgetSort] = useState<SortKey>("win_prob");
  const [budgetFilter, setBudgetFilter] = useState<FilterKey>("all");

  const topItems = useMemo(
    () => sortSignals(filterSignals(topOpportunities, topFilter), topSort),
    [topOpportunities, topFilter, topSort],
  );

  const budgetItems = useMemo(
    () => sortSignals(filterSignals(budgetOpportunities, budgetFilter), budgetSort),
    [budgetOpportunities, budgetFilter, budgetSort],
  );

  return (
    <>
      <section className="mb-8">
        <SectionHeader title="Top Opportunities Today" />
        <SignalsToolbar
          sort={topSort}
          filter={topFilter}
          onSortChange={setTopSort}
          onFilterChange={setTopFilter}
          resultCount={topItems.length}
        />
        <OpportunityList
          items={topItems}
          highlightBudget
          emptyMessage='No signals yet. Click "Deep scan market" above to hunt across movers, actives, and growth names.'
        />
      </section>

      {/* Sports featured — 24/7 priority module */}
      <section className="mb-8 overflow-hidden rounded-2xl border border-violet-500/35 bg-gradient-to-br from-violet-600/15 via-violet-500/8 to-surface p-5 sm:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-violet-600 px-2.5 py-0.5 text-[10px] font-bold text-white">
                24/7
              </span>
              {sportsOpportunities.length > 0 && (
                <span className="rounded-full bg-violet-500/25 px-2 py-0.5 text-xs font-semibold text-violet-200">
                  {sportsOpportunities.length} plays
                </span>
              )}
            </div>
            <SectionHeader
              title="Sports +EV Picks"
              description="NBA, NFL, MLB, NHL, soccer & more — ranked by edge vs FanDuel. Scan → pick #1 → build parlays."
              href="/sports"
            />
          </div>
          <Link
            href="/parlays"
            className="shrink-0 rounded-lg bg-orange-500 px-3 py-2 text-xs font-bold text-white hover:bg-orange-500/90"
          >
            Build parlays →
          </Link>
        </div>
        <OpportunityList
          items={sportsOpportunities}
          emptyMessage='No sports plays yet. Click "Scan sports odds" in the scanner bar — leagues run around the clock worldwide.'
          moduleLinkBase="/sports"
        />
        {sportsOpportunities.length > 0 && (
          <Link
            href="/sports"
            className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-violet-300 hover:text-violet-200 hover:underline"
          >
            Open full sports command center →
          </Link>
        )}
      </section>

      <section className="mb-8">
        <SectionHeader
          title="Stock Swing Picks"
          description="RSI, MACD, and volume-ranked swing trades with entry zones and stops."
          href="/stocks"
          count={stockOpportunities.length}
        />
        <OpportunityList
          items={stockOpportunities}
          emptyMessage='No stock swings yet. Click "Scan stock swings" in the scanner bar above.'
          moduleLinkBase="/stocks"
        />
      </section>

      <section className="mb-8">
        <SectionHeader
          title="Budget Picks · Under $100 / Contract"
          description="Same deep scan and scoring — filtered to options costing $100 or less per contract."
        />
        <SignalsToolbar
          sort={budgetSort}
          filter={budgetFilter}
          onSortChange={setBudgetSort}
          onFilterChange={setBudgetFilter}
          resultCount={budgetItems.length}
        />
        <OpportunityList
          items={budgetItems}
          highlightBudget
          showContractCost
          emptyMessage="No budget picks match your filters. Run a deep scan or loosen filters."
        />
      </section>
    </>
  );
}
