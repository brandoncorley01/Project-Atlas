import Link from "next/link";

const STEPS = [
  {
    step: 1,
    color: "border-sky-500/40 bg-sky-500/10",
    badge: "bg-sky-600",
    title: "Scan the market",
    body: "Use the scanner bar: Options, Stocks, or Odds + Parlays for a full sports workflow.",
    link: { href: "/", label: "Go to scanner" },
  },
  {
    step: 2,
    color: "border-emerald-500/40 bg-emerald-500/10",
    badge: "bg-emerald-600",
    title: "Pick the #1 ranked play",
    body: "Each card shows Confidence, Risk, and Opportunity scores. Higher confidence + opportunity = stronger pick. Tap a card for full details.",
    link: { href: "/options", label: "View options" },
  },
  {
    step: 3,
    color: "border-violet-500/40 bg-violet-500/10",
    badge: "bg-violet-600",
    title: "Sports → build parlays",
    body: "Scan sports odds first, then open Parlays and click Build parlay options. Conservative = safest, Aggressive = biggest payout.",
    link: { href: "/parlays", label: "Build parlays" },
  },
  {
    step: 4,
    color: "border-amber-500/40 bg-amber-500/10",
    badge: "bg-amber-500",
    title: "Read the news behind the move",
    body: "Every headline links to the original article. Bullish news can boost options scores — check the News board before you trade.",
    link: { href: "/news", label: "News board" },
  },
] as const;

export function QuickStartGuide({ compact }: { compact?: boolean }) {
  return (
    <section className={`atlas-card border-accent/20 bg-gradient-to-br from-accent-muted to-surface p-5 ${compact ? "" : "mb-8"}`}>
      <div className="mb-4">
        <h2 className="text-lg font-bold text-foreground">New here? Start in 4 steps</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          No finance degree needed — Atlas ranks opportunities so you can follow the highest-scored
          picks. Hover dotted terms throughout the app for plain-English definitions.
        </p>
      </div>

      <div className={`grid gap-3 ${compact ? "sm:grid-cols-2" : "md:grid-cols-2 lg:grid-cols-4"}`}>
        {STEPS.map((s) => (
          <div
            key={s.step}
            className={`rounded-xl border p-4 ${s.color}`}
          >
            <span
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white ${s.badge}`}
            >
              {s.step}
            </span>
            <h3 className="mt-2 text-sm font-bold text-foreground">{s.title}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted">{s.body}</p>
            <Link
              href={s.link.href}
              className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
            >
              {s.link.label} →
            </Link>
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs text-muted/80">
        Decision support only — not financial advice. Past performance does not guarantee future results.
      </p>
    </section>
  );
}
