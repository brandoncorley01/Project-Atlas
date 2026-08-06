import type { OptionSignal } from "@/components/options/OptionSignalCard";

/** Rows in `all` that are not already shown in the budget board. */
export function exclusiveAllOptions(
  allItems: OptionSignal[],
  budgetItems: OptionSignal[],
): OptionSignal[] {
  const budgetIds = new Set(budgetItems.map((r) => r.id).filter(Boolean));
  if (budgetIds.size === 0) return allItems;
  return allItems.filter((r) => !budgetIds.has(r.id));
}

/** True when capital-first persisted only budget rows (All would be a duplicate list). */
export function isCapitalFirstOnlyBoard(
  allItems: OptionSignal[],
  budgetItems: OptionSignal[],
): boolean {
  const exclusive = exclusiveAllOptions(allItems, budgetItems);
  return budgetItems.length > 0 && exclusive.length === 0 && allItems.length > 0;
}
