"use client";

import { DataStatusBadge } from "@/components/market-intelligence/DataStatusBadge";

export function OptionsTradeCard({ card }: { card: Record<string, unknown> }) {
  const score = (card.score as Record<string, unknown> | undefined) ?? {};
  const warnings = Array.isArray(card.warnings) ? (card.warnings as string[]) : [];
  const direction = String(card.direction ?? "uncertain").replaceAll("_", " ");
  return (
    <article className="rounded-xl border border-border bg-surface/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-foreground">{String(card.ticker ?? "—")}</h3>
          <p className="text-sm text-muted">{String(card.contract ?? "")}</p>
        </div>
        <DataStatusBadge status={String(card.data_status ?? "simulated")} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted">Direction</dt>
          <dd className="font-medium capitalize">{direction}</dd>
        </div>
        <div>
          <dt className="text-muted">Unusual score</dt>
          <dd className="font-medium">{String(card.unusual_score ?? "—")}</dd>
        </div>
        <div>
          <dt className="text-muted">Confidence</dt>
          <dd className="font-medium">{String(card.atlas_confidence ?? "—")}</dd>
        </div>
        <div>
          <dt className="text-muted">Liquidity</dt>
          <dd className="font-medium">{String(card.liquidity_grade ?? "—")}</dd>
        </div>
        <div>
          <dt className="text-muted">Premium</dt>
          <dd className="font-medium">{String(card.current_premium ?? "—")}</dd>
        </div>
        <div>
          <dt className="text-muted">Vol / OI</dt>
          <dd className="font-medium">{String(card.volume_oi_ratio ?? "—")}</dd>
        </div>
        <div>
          <dt className="text-muted">Spread %</dt>
          <dd className="font-medium">
            {card.bid_ask_spread_pct != null ? Number(card.bid_ask_spread_pct).toFixed(1) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Risk</dt>
          <dd className="font-medium capitalize">{String(card.risk_level ?? "—")}</dd>
        </div>
      </dl>

      <p className="mt-3 text-sm text-foreground/90">{String(card.explanation ?? "")}</p>
      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-amber-200/90">
          {warnings.slice(0, 4).map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[11px] text-muted">
        Review zone: {String((card.suggested_review_zone as { note?: string })?.note ?? "Not a guaranteed entry")}
        {score.data_quality ? ` · Data quality ${String(score.data_quality)}` : ""}
        {score.score_version ? ` · ${String(score.score_version)}` : ""}
      </p>
    </article>
  );
}
