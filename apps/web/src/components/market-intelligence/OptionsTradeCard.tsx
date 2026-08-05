"use client";

import Link from "next/link";
import { DataStatusBadge } from "@/components/market-intelligence/DataStatusBadge";
import { stanceForOptionsCard, stanceToneClass } from "@/lib/market-intelligence-decisions";

export function OptionsTradeCard({
  card,
  compact = false,
}: {
  card: Record<string, unknown>;
  compact?: boolean;
}) {
  const score = (card.score as Record<string, unknown> | undefined) ?? {};
  const warnings = Array.isArray(card.warnings) ? (card.warnings as string[]) : [];
  const direction = String(card.direction ?? "uncertain").replaceAll("_", " ");
  const stance = stanceForOptionsCard(card);
  const contributors = Array.isArray(score.positive_contributors)
    ? (score.positive_contributors as string[])
    : [];

  return (
    <article className="rounded-xl border border-border bg-surface/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{String(card.ticker ?? "—")}</h3>
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${stanceToneClass(stance.id)}`}
            >
              {stance.label}
            </span>
          </div>
          <p className="text-sm text-muted">{String(card.contract ?? "")}</p>
        </div>
        <DataStatusBadge status={String(card.data_status ?? "simulated")} />
      </div>

      <p className="mt-2 text-xs text-muted">{stance.detail}</p>

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
        {!compact && (
          <>
            <div>
              <dt className="text-muted">Premium</dt>
              <dd className="font-medium">
                {card.current_premium != null ? `$${Number(card.current_premium).toFixed(2)}` : "—"}
              </dd>
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
          </>
        )}
      </dl>

      {!compact && (
        <>
          <p className="mt-3 text-sm text-foreground/90">{String(card.explanation ?? "")}</p>
          {contributors.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-foreground/85">
              {contributors.slice(0, 3).map((c) => (
                <li key={c}>◆ {c}</li>
              ))}
            </ul>
          )}
          {warnings.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-amber-200/90">
              {warnings.slice(0, 4).map((w) => (
                <li key={w}>⚠ {w}</li>
              ))}
            </ul>
          )}
        </>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-muted">
        <span>
          Review zone:{" "}
          {String((card.suggested_review_zone as { note?: string })?.note ?? "Not a guaranteed entry")}
        </span>
        {score.data_quality ? <span>· Data quality {String(score.data_quality)}</span> : null}
        <Link href="/options" className="font-semibold text-accent hover:underline">
          Open Options board →
        </Link>
      </div>
    </article>
  );
}
