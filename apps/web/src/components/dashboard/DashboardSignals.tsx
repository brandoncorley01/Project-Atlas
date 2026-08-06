"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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

  const budgetIds = useMemo(
    () => new Set(budgetOpportunities.map((r) => r.id).filter(Boolean)),
    [budgetOpportunities],
  );

  // Non-budget rows that would uniquely appear on Top.
  const topNonBudget = useMemo(() => {
    if (budgetIds.size === 0) return topOpportunities;
    return topOpportunities.filter((item) => !budgetIds.has(item.id));
  }, [topOpportunities, budgetIds]);

  // Capital-first: Top and Budget are the same saved set.
  const capitalFirstOnly =
    budgetOpportunities.length > 0 && topNonBudget.length === 0 && topOpportunities.length > 0;

  // During capital-first, Top IS the under-$100 board (don't leave Top empty).
  const topExclusive = capitalFirstOnly ? budgetOpportunities : topNonBudget;

  useEffect(() => {
    if (capitalFirstOnly && tab === "budget") setTab("top");
  }, [capitalFirstOnly, tab]);

  const tabs: { id: BoardTab; label: string; count: number; href: string }[] = [
    { id: "top", label: "Top", count: topExclusive.length, href: "/" },
    { id: "sports", label: "Sports", count: sportsOpportunities.length, href: "/sports" },
    { id: "stocks", label: "Stocks", count: stockOpportunities.length, href: "/stocks" },
    ...(!capitalFirstOnly
      ? [{ id: "budget" as const, label: "Budget", count: budgetOpportunities.length, href: "/options" }]
      : []),
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
    top: "No signals yet. Use the scanner bar above — Options, Stocks, or Sports.",
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
          description={
            capitalFirstOnly
              ? "Capital-first mode — Top shows under-$100 options until Atlas proves its win rate."
              : "One board — switch modules without scrolling past duplicates."
          }
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
        highlightBudget={tab === "budget" || (tab === "top" && capitalFirstOnly)}
        showContractCost={tab === "budget" || (tab === "top" && capitalFirstOnly)}
        emptyMessage={emptyByTab[tab]}
        moduleLinkBase={
          tab === "sports" ? "/sports" : tab === "stocks" ? "/stocks" : tab === "budget" ? "/options" : "/options"
        }
      />
    </section>
  );
}
