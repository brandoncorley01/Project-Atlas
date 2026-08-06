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

type BoardTab = "top" | "sports" | "stocks" | "budget";

export function DashboardSignals({
  topOpportunities,
  budgetOpportunities,
  stockOpportunities,
  sportsOpportunities,
}: DashboardSignalsProps) {
  const [tab, setTab] = useState<BoardTab>("top");
  const [sort, setSort] = useState<SortKey>("win_prob");
  const [filter, setFilter] = useState<FilterKey>("all");

  // Capital-first scans make Top (list_options) and Budget the same IDs — exclude
  // budget rows from Top so Home never lists one options contract twice.
  const topExclusive = useMemo(() => {
    const budgetIds = new Set(budgetOpportunities.map((r) => r.id).filter(Boolean));
    if (budgetIds.size === 0) return topOpportunities;
    return topOpportunities.filter((item) => !budgetIds.has(item.id));
  }, [topOpportunities, budgetOpportunities]);

  const tabs: { id: BoardTab; label: string; count: number; href: string }[] = [
    { id: "top", label: "Top", count: topExclusive.length, href: "/" },
    { id: "sports", label: "Sports", count: sportsOpportunities.length, href: "/sports" },
    { id: "stocks", label: "Stocks", count: stockOpportunities.length, href: "/stocks" },
    { id: "budget", label: "Budget", count: budgetOpportunities.length, href: "/options" },
  ];

  const source = useMemo(() => {
    switch (tab) {
      case "sports":
        return sportsOpportunities;
      case "stocks":
        return stockOpportunities;
      case "budget":
        return budgetOpportunities;
      default:
        return topExclusive;
    }
  }, [tab, topExclusive, sportsOpportunities, stockOpportunities, budgetOpportunities]);

  const items = useMemo(
    () => sortSignals(filterSignals(source, filter), sort),
    [source, filter, sort],
  );

  const emptyByTab: Record<BoardTab, string> = {
    top:
      budgetOpportunities.length > 0 && topExclusive.length === 0
        ? "Capital-first mode — under-$100 options are on the Budget tab until Atlas proves its win rate."
        : "No signals yet. Use the scanner bar above — Options, Stocks, or Sports.",
    sports: "No sports plays yet. Tap Sports → Scan sports odds.",
    stocks: "No stock swings yet. Tap Stocks → Scan stock swings.",
    budget: "No budget options yet. Run a deep options scan.",
  };

  const activeHref = tabs.find((t) => t.id === tab)?.href ?? "/";

  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <SectionHeader
          title="Opportunities"
          description="One board — switch modules without scrolling past duplicates."
        />
        {tab !== "top" && (
          <Link href={activeHref} className="text-xs font-semibold text-accent hover:underline">
            Open {tab} →
          </Link>
        )}
      </div>

      <div className="mb-3 flex gap-1 overflow-x-auto rounded-lg border border-border bg-surface-elevated p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              tab === t.id
                ? "bg-accent/20 text-accent"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            }`}
          >
            {t.label}
            {t.count > 0 ? ` · ${t.count}` : ""}
          </button>
        ))}
      </div>

      <SignalsToolbar
        sort={sort}
        filter={filter}
        onSortChange={setSort}
        onFilterChange={setFilter}
        resultCount={items.length}
      />
      <OpportunityList
        items={items}
        highlightBudget={tab === "budget" || tab === "top"}
        showContractCost={tab === "budget"}
        emptyMessage={emptyByTab[tab]}
        moduleLinkBase={
          tab === "sports" ? "/sports" : tab === "stocks" ? "/stocks" : tab === "budget" ? "/options" : undefined
        }
      />
    </section>
  );
}
