import type { SignalSummary } from "@/components/dashboard/OpportunityList";

export type SortKey = "win_prob" | "opportunity" | "risk_low" | "cost_low" | "dte";
export type FilterKey = "all" | "budget" | "calls" | "puts" | "catalyst";

export function getWinProb(item: SignalSummary): number {
  return Number(item.context?.profit_probability ?? 0);
}

export function isBudget(item: SignalSummary): boolean {
  return Boolean(item.is_budget ?? (item.contract_cost != null && item.contract_cost <= 100));
}

export function getOptionType(item: SignalSummary): string {
  const parts = item.title.split(" ");
  return parts[1]?.toLowerCase() ?? "";
}

export function getDte(item: SignalSummary): number {
  if (!item.expiration) return 999;
  const exp = new Date(`${item.expiration}T12:00:00`);
  const now = new Date();
  return Math.max(0, Math.ceil((exp.getTime() - now.getTime()) / 86400000));
}

export function filterSignals(items: SignalSummary[], filter: FilterKey): SignalSummary[] {
  switch (filter) {
    case "budget":
      return items.filter(isBudget);
    case "calls":
      return items.filter((i) => getOptionType(i) === "call");
    case "puts":
      return items.filter((i) => getOptionType(i) === "put");
    case "catalyst":
      return items.filter((i) => Boolean(i.context?.has_catalyst || i.context?.top_headline));
    default:
      return items;
  }
}

export function sortSignals(items: SignalSummary[], sort: SortKey): SignalSummary[] {
  const copy = [...items];
  copy.sort((a, b) => {
    switch (sort) {
      case "win_prob":
        return getWinProb(b) - getWinProb(a);
      case "opportunity":
        return b.scores.opportunity - a.scores.opportunity;
      case "risk_low":
        return a.scores.risk - b.scores.risk;
      case "cost_low":
        return (a.contract_cost ?? 9999) - (b.contract_cost ?? 9999);
      case "dte":
        return getDte(a) - getDte(b);
      default:
        return 0;
    }
  });
  return copy;
}
