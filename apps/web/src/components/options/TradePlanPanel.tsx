export interface ItmMilestone {
  date: string;
  label: string;
  title: string;
  itm_probability_pct: number;
  status: "likely" | "building" | "unlikely";
  status_label: string;
}

export interface PurchaseWindow {
  start_date: string;
  end_date: string;
  label: string;
  friendly: string;
  reason: string;
}

export interface StrategyOption {
  id: string;
  name: string;
  badge: string;
  difficulty: "Beginner" | "Intermediate";
  rank: number;
  win_probability: number;
  cost_per_contract: number | null;
  max_loss: string;
  max_profit: string;
  best_for: string;
  purchase_window: string;
  summary: string;
}

export interface TradePlan {
  expiration_date: string;
  expiration_label: string;
  stock_price: number;
  breakeven_price: number;
  move_needed_pct: number;
  currently_itm: boolean;
  purchase_window: PurchaseWindow;
  itm_timeline: ItmMilestone[];
  strategies: StrategyOption[];
  recommended_strategy_id: string;
  beginner_tip: string;
}

const STATUS_STYLES = {
  likely: "bg-success/20 border-success/40 text-success",
  building: "bg-warning/15 border-warning/40 text-warning",
  unlikely: "bg-background border-border text-muted",
} as const;

export function PurchaseWindowCard({ window }: { window: PurchaseWindow }) {
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/10 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">When to buy</p>
      <p className="mt-1 text-lg font-bold">{window.label}</p>
      <p className="mt-1 text-sm text-muted">{window.friendly}</p>
      <p className="mt-2 text-sm leading-relaxed">{window.reason}</p>
    </div>
  );
}

export function ItmTimeline({ timeline, expirationLabel }: { timeline: ItmMilestone[]; expirationLabel: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/50 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          In-the-money odds over time
        </p>
        <p className="text-xs text-muted">Expires {expirationLabel}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {timeline.map((step) => (
          <div
            key={`${step.date}-${step.title}`}
            className={`rounded-lg border p-3 ${STATUS_STYLES[step.status]}`}
          >
            <p className="text-xs font-medium uppercase opacity-80">{step.title}</p>
            <p className="mt-1 text-sm font-semibold">{step.label}</p>
            <p className="mt-2 text-2xl font-bold">{step.itm_probability_pct}%</p>
            <p className="mt-1 text-xs leading-snug">{step.status_label}</p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/20">
              <div
                className="h-full rounded-full bg-current opacity-70"
                style={{ width: `${step.itm_probability_pct}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <p className="mt-3 text-xs text-muted">
        &quot;In the money&quot; means the stock price is past your strike — your option has real value.
      </p>
    </div>
  );
}

export function StrategyComparison({ strategies }: { strategies: StrategyOption[] }) {
  return (
    <div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
        Compare strategies
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        {strategies.map((strategy, index) => (
          <div
            key={strategy.id}
            className={`rounded-xl border p-4 ${
              index === 0 ? "border-success/40 bg-success/5" : "border-border bg-surface"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-xs text-muted">#{index + 1}</p>
                <h4 className="font-semibold">{strategy.name}</h4>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <span className="rounded-md bg-accent/15 px-2 py-0.5 text-xs text-accent">
                  {strategy.badge}
                </span>
                <span className="rounded-md bg-background px-2 py-0.5 text-xs text-muted">
                  {strategy.difficulty}
                </span>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-background/60 p-2">
                <p className="text-xs text-muted">Win odds</p>
                <p className="font-bold text-success">{strategy.win_probability}%</p>
              </div>
              <div className="rounded-lg bg-background/60 p-2">
                <p className="text-xs text-muted">Buy window</p>
                <p className="font-medium">{strategy.purchase_window}</p>
              </div>
              <div className="rounded-lg bg-background/60 p-2">
                <p className="text-xs text-muted">Max loss</p>
                <p className="font-medium">{strategy.max_loss}</p>
              </div>
              <div className="rounded-lg bg-background/60 p-2">
                <p className="text-xs text-muted">Max profit</p>
                <p className="font-medium leading-snug">{strategy.max_profit}</p>
              </div>
            </div>

            <p className="mt-3 text-xs text-muted">
              <span className="font-medium text-foreground">Best for: </span>
              {strategy.best_for}
            </p>
            <p className="mt-2 text-sm leading-relaxed">{strategy.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TradePlanPanel({ plan }: { plan: TradePlan }) {
  return (
    <div className="space-y-4 border-t border-border pt-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-background/40 p-3">
          <p className="text-xs text-muted">Stock now</p>
          <p className="text-lg font-bold">${plan.stock_price.toFixed(2)}</p>
        </div>
        <div className="rounded-lg border border-border bg-background/40 p-3">
          <p className="text-xs text-muted">Breakeven</p>
          <p className="text-lg font-bold">${plan.breakeven_price.toFixed(2)}</p>
        </div>
        <div className="rounded-lg border border-border bg-background/40 p-3">
          <p className="text-xs text-muted">Move needed</p>
          <p className="text-lg font-bold">{plan.move_needed_pct.toFixed(1)}%</p>
        </div>
      </div>

      <PurchaseWindowCard window={plan.purchase_window} />
      <ItmTimeline timeline={plan.itm_timeline} expirationLabel={plan.expiration_label} />
      <StrategyComparison strategies={plan.strategies} />

      <div className="rounded-xl border border-border bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent">Beginner tip</p>
        <p className="mt-2 text-sm leading-relaxed">{plan.beginner_tip}</p>
      </div>
    </div>
  );
}
