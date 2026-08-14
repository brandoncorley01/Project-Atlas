"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { OptionSignalCard, type OptionSignal } from "@/components/options/OptionSignalCard";
import { AtlasModuleInsight } from "@/components/ai/AtlasModuleInsight";
import { SignalsToolbar } from "@/components/dashboard/SignalsToolbar";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { QuickStartGuide } from "@/components/ui/QuickStartGuide";
import { filterSignals, sortSignals, type FilterKey, type SortKey } from "@/lib/signal-filters";
import type { SignalSummary } from "@/components/dashboard/OpportunityList";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import {
  exclusiveAllOptions,
  isCapitalFirstOnlyBoard,
} from "@/lib/options-signals-dedupe";
import { formatStrike } from "@/lib/format-strike";

function toSummary(row: OptionSignal): SignalSummary {
  const ctx = row.scoring_snapshot?.market_context as SignalSummary["context"] | undefined;
  const premium = Number(row.premium ?? 0);
  const contractCost = row.contract_cost ?? premium * 100;
  const optionType = (row.option_type ?? "option").toUpperCase();
  return {
    id: row.id,
    module: "options",
    title: `${row.underlying} ${optionType} $${formatStrike(row.strike)}`,
    recommendation: row.recommendation,
    context: {
      ...ctx,
      profit_probability: row.scoring_snapshot?.profit_probability as number | undefined,
    },
    expiration: row.expiration,
    contract_cost: contractCost,
    is_budget: row.is_budget ?? contractCost <= 100,
    premium,
    scores: {
      confidence: row.confidence_score,
      risk: row.risk_score,
      opportunity: row.opportunity_score,
    },
  };
}

interface OptionsListResponse {
  items: OptionSignal[];
}

interface OptionsSignalsViewProps {
  initialAllItems?: OptionSignal[];
  initialBudgetItems?: OptionSignal[];
}

async function getToken(): Promise<string | undefined> {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

export function OptionsSignalsView({
  initialAllItems = [],
  initialBudgetItems = [],
}: OptionsSignalsViewProps) {
  const router = useRouter();
  const [allItems, setAllItems] = useState(initialAllItems);
  const [budgetItems, setBudgetItems] = useState(initialBudgetItems);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [topSort, setTopSort] = useState<SortKey>("win_prob");
  const [topFilter, setTopFilter] = useState<FilterKey>("all");
  const [budgetSort, setBudgetSort] = useState<SortKey>("win_prob");
  const [budgetFilter, setBudgetFilter] = useState<FilterKey>("all");

  const loadOptions = useCallback(async () => {
    setLoading(true);
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setLoading(false);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const [allRes, budgetRes] = await Promise.all([
        fetch(`${apiUrl}/signals/options?limit=20`, {
          headers: apiRequestHeaders(token),
          cache: "no-store",
        }),
        fetch(`${apiUrl}/signals/options?limit=12&budget=true`, {
          headers: apiRequestHeaders(token),
          cache: "no-store",
        }),
      ]);

      if (!allRes.ok || !budgetRes.ok) {
        const failed = !allRes.ok ? allRes : budgetRes;
        let detail = "Could not load options picks";
        try {
          const body = await failed.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          // ignore parse errors
        }
        setMessage(detail);
        setLoading(false);
        return;
      }

      const [allData, budgetData] = (await Promise.all([
        allRes.json(),
        budgetRes.json(),
      ])) as [OptionsListResponse, OptionsListResponse];

      setAllItems(allData.items ?? []);
      setBudgetItems(budgetData.items ?? []);
    } catch {
      setMessage(
        usesBffProxy()
          ? "Atlas API is temporarily unavailable. Try again in a moment."
          : "Backend not responding — run .\\scripts\\start-dev.ps1",
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  async function refreshOptions() {
    setScanning(true);
    setMessage(null);

    const token = await getToken();
    if (!usesBffProxy() && !token) {
      setMessage("Not signed in");
      setScanning(false);
      return;
    }

    const apiUrl = getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/engine/refresh-options`, {
        method: "POST",
        headers: apiRequestHeaders(token),
        signal: AbortSignal.timeout(300_000),
      });
      const body = await res.json();
      if (!res.ok || body.ok === false || body.status === "error") {
        const detail =
          (typeof body.message === "string" && body.message) ||
          (typeof body.detail === "string" && body.detail) ||
          "Options scan failed";
        setMessage(detail);
        setScanning(false);
        return;
      }

      const created = body.signals_created as number | undefined;
      const stats = (body.stats ?? {}) as { symbols_scanned?: number };
      const scanned =
        (body.symbols_scanned as number | undefined) ?? stats.symbols_scanned;
      const modeNote =
        typeof body.message === "string" && body.message.trim() ? body.message.trim() : null;
      if (created != null && created > 0) {
        setMessage(
          modeNote
            ? `Found ${created} options setups · scanned ${scanned ?? "?"} symbols. ${modeNote}`
            : `Found ${created} options setups · scanned ${scanned ?? "?"} symbols`,
        );
      } else {
        setMessage(modeNote ?? "No setups met the score threshold");
      }

      await loadOptions();
      router.refresh();
    } catch {
      setMessage(
        usesBffProxy()
          ? "Options scan timed out or API is unavailable. Try again in a moment."
          : "Backend not responding — run .\\scripts\\start-dev.ps1",
      );
    }
    setScanning(false);
  }

  const budgetOrdered = useMemo(() => {
    const summaries = sortSignals(filterSignals(budgetItems.map(toSummary), budgetFilter), budgetSort);
    const byId = new Map(budgetItems.map((r) => [r.id, r]));
    return summaries.map((s) => byId.get(s.id)).filter(Boolean) as OptionSignal[];
  }, [budgetItems, budgetFilter, budgetSort]);

  // Capital-first scans persist only under-$100 rows, so /signals/options and
  // ?budget=true return the same IDs. Exclude budget rows from "All scanned"
  // so the page never lists the same contract twice.
  const allExclusiveItems = useMemo(
    () => exclusiveAllOptions(allItems, budgetItems),
    [allItems, budgetItems],
  );

  const topOrdered = useMemo(() => {
    const summaries = sortSignals(
      filterSignals(allExclusiveItems.map(toSummary), topFilter),
      topSort,
    );
    const byId = new Map(allExclusiveItems.map((r) => [r.id, r]));
    return summaries.map((s) => byId.get(s.id)).filter(Boolean) as OptionSignal[];
  }, [allExclusiveItems, topFilter, topSort]);

  const busy = loading || scanning;
  const hasAny = allItems.length > 0 || budgetItems.length > 0;
  const capitalFirstOnly = isCapitalFirstOnlyBoard(allItems, budgetItems);
  const insightRow = budgetOrdered[0] ?? topOrdered[0] ?? allItems[0];

  if (loading && !hasAny) {
    return (
      <div className="space-y-6">
        <ListSkeleton count={3} />
      </div>
    );
  }

  if (!hasAny && !loading) {
    return (
      <div className="space-y-6">
        {!message && <QuickStartGuide compact />}
        {message && (
          <p className="rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-muted">
            {message}
          </p>
        )}
        <EmptyState
          title="No options picks yet"
          description='Tap "Deep scan market" below. Atlas ranks call and put setups by confidence and profit odds.'
          action={
            <button
              type="button"
              onClick={refreshOptions}
              disabled={busy}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {scanning ? "Scanning…" : "Deep scan market"}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <AtlasModuleInsight
        module="options"
        signalId={insightRow?.id}
        headline="Options move on time — Atlas prioritizes catalysts, DTE, and premium velocity."
        urgencyNote={
          insightRow && Number(insightRow.days_to_expiration ?? 99) <= 14
            ? `Top pick has ${Number(insightRow.days_to_expiration)} DTE — near-term monetary risk/reward is elevated.`
            : "Short-dated contracts reprice faster than stocks — size carefully."
        }
      />

      <Link
        href="/options-intelligence"
        className="block rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 transition-colors hover:bg-cyan-500/15"
      >
        <p className="text-sm font-semibold text-foreground">Options Intelligence →</p>
        <p className="mt-0.5 text-xs text-muted">
          Flow scanner, low-premium opportunities, concentrated activity, and options heatmaps.
        </p>
      </Link>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Ranked by profit probability · expand any card for entry, breakeven, and trade plan.
        </p>
        <button
          type="button"
          onClick={refreshOptions}
          disabled={busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-accent/20 disabled:opacity-50"
        >
          {scanning ? "Scanning…" : "Deep scan market"}
        </button>
      </div>

      {message && (
        <p className="rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-muted">
          {message}
        </p>
      )}

      <div className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3">
        <p className="text-sm font-semibold text-emerald-200">Capital-first options</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Atlas prioritizes contracts under <strong className="text-foreground">$100</strong> until
          it has proven a real options win rate (15+ graded picks at ≥55%). The goal is to keep
          money in your pocket while the model learns — not to push expensive contracts early.
        </p>
      </div>

      <section>
        <h2 className="mb-1 text-lg font-semibold">Under $100 Per Contract</h2>
        <p className="mb-2 text-sm text-muted">
          Primary board — one contract costs $100 or less. Ranked by profit probability.
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
              <OptionSignalCard
                key={row.id || `${row.underlying}-${row.option_type}-${row.strike}-${row.expiration}`}
                row={row}
                rank={index + 1}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-surface/50 p-6 text-center text-sm text-muted">
            No budget picks match your filters — run a deep scan during market hours.
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold">All scanned picks</h2>
        <p className="mb-2 text-sm text-muted">
          Higher-cost contracts from the same scan. While Atlas is still proving itself, deep
          scan saves under-$100 contracts first — those stay in the section above.
        </p>
        {capitalFirstOnly ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/50 p-6 text-center text-sm text-muted">
            Capital-first mode is on — only under-$100 contracts are saved until Atlas proves a
            ≥55% options win rate on 15+ graded picks. Re-scan after that to unlock higher-cost
            plays here.
          </div>
        ) : (
          <>
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
                  <OptionSignalCard
                    key={row.id || `${row.underlying}-${row.option_type}-${row.strike}-${row.expiration}`}
                    row={row}
                    rank={index + 1}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No picks match your filters.</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
