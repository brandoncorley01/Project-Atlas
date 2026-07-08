"use client";

export interface MarketIntelligence {
  headline?: string;
  summary?: string;
  patterns?: string[];
  edge_notes?: string[];
  regime?: string | null;
  sample_count?: number;
  source?: string;
}

export interface TrackingStats {
  total_tracked?: number;
  auto_pending?: number;
  auto_resolved?: number;
  manual_logged?: number;
  watchlist_tracked?: number;
  by_module?: Record<string, { total?: number; pending?: number; resolved?: number }>;
}

interface MarketIntelligenceCardProps {
  intelligence?: MarketIntelligence | null;
  tracking?: TrackingStats | null;
}

export function MarketIntelligenceCard({ intelligence, tracking }: MarketIntelligenceCardProps) {
  const total = tracking?.total_tracked ?? 0;
  const autoResolved = tracking?.auto_resolved ?? 0;
  const autoPending = tracking?.auto_pending ?? 0;

  if (!intelligence?.headline && total === 0) {
    return (
      <section className="mb-8 rounded-xl border border-dashed border-violet-500/30 bg-violet-500/5 p-4">
        <h2 className="text-sm font-semibold text-violet-100">Atlas market intelligence</h2>
        <p className="mt-2 text-sm text-muted">
          Every scan auto-registers picks for outcome tracking — you don&apos;t need to save or watchlist them.
          Atlas grades sports, stocks, and options when they expire, then AI analyzes patterns to sharpen future scans.
        </p>
      </section>
    );
  }

  const isAi = intelligence?.source === "openai";

  return (
    <section className="mb-8 rounded-xl border border-violet-500/30 bg-gradient-to-br from-violet-500/10 to-transparent p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-violet-100">Atlas market intelligence</h2>
            {isAi && (
              <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-violet-200">
                AI
              </span>
            )}
          </div>
          <p className="mt-1 text-base font-medium text-foreground">
            {intelligence?.headline ?? "Learning from every pick"}
          </p>
        </div>
        <div className="flex gap-4 text-center text-xs">
          <div>
            <p className="text-lg font-semibold text-foreground">{total}</p>
            <p className="text-muted">Tracked</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-success">{autoResolved}</p>
            <p className="text-muted">Auto-graded</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-amber-200">{autoPending}</p>
            <p className="text-muted">Awaiting</p>
          </div>
        </div>
      </div>

      {intelligence?.summary && (
        <p className="mt-3 text-sm leading-relaxed text-muted">{intelligence.summary}</p>
      )}

      {intelligence?.regime && (
        <p className="mt-2 text-xs font-medium text-violet-200">
          Market regime: {intelligence.regime}
        </p>
      )}

      {intelligence?.patterns && intelligence.patterns.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {intelligence.patterns.map((p) => (
            <li key={p} className="flex gap-2 text-sm text-foreground/90">
              <span className="text-violet-400" aria-hidden>
                ◆
              </span>
              {p}
            </li>
          ))}
        </ul>
      )}

      {intelligence?.edge_notes && intelligence.edge_notes.length > 0 && (
        <div className="mt-4 rounded-lg border border-violet-500/20 bg-violet-500/5 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-200/80">Edge notes</p>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {intelligence.edge_notes.map((n) => (
              <li key={n}>· {n}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
