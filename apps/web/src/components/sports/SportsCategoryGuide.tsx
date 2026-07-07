import type { SportsCategoryMeta } from "@/lib/sports-categories";

export function SportsCategoryGuide({ category }: { category: SportsCategoryMeta }) {
  return (
    <section className="mb-8 rounded-xl border border-violet-500/30 bg-violet-500/5 p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-violet-300">
        {category.title} · How to use this view
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">{category.description}</p>
      <div className="mt-4 rounded-lg border border-border bg-background/60 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Full explanation</p>
        <p className="mt-2 text-sm leading-relaxed text-foreground">{category.guide}</p>
      </div>
      <p className="mt-3 text-xs text-muted">
        {category.count} active play{category.count === 1 ? "" : "s"} in this category · odds from
        FanDuel with multi-book comparison · news matched from ESPN, CBS Sports, and BBC Sport RSS.
      </p>
    </section>
  );
}
