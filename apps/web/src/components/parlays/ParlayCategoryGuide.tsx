import type { ParlayCategoryMeta } from "@/lib/parlay-categories";

export function ParlayCategoryGuide({ category }: { category: ParlayCategoryMeta }) {
  return (
    <section className="mb-8 rounded-xl border border-orange-500/30 bg-orange-500/5 p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-orange-300">
        {category.title} · How to use this view
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">{category.description}</p>
      <div className="mt-4 rounded-lg border border-border bg-background/60 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Full explanation</p>
        <p className="mt-2 text-sm leading-relaxed text-foreground">{category.guide}</p>
      </div>
      <p className="mt-3 text-xs text-muted">
        {category.count} active parlay{category.count === 1 ? "" : "s"} in this category · only
        upcoming legs shown · finished games are expired automatically.
      </p>
    </section>
  );
}
