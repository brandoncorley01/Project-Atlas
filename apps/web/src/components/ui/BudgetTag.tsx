export function BudgetTag({ cost }: { cost?: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 px-2.5 py-1 text-xs font-bold text-white shadow-md shadow-emerald-500/25">
      <span aria-hidden>💰</span>
      Under $100{cost != null ? ` · $${Math.round(cost)}` : ""}
    </span>
  );
}
