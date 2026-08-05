"use client";

import { DataStatusBadge } from "@/components/market-intelligence/DataStatusBadge";

type Rec = Record<string, unknown>;

function recTone(rec: string) {
  if (rec === "QUALIFIED_TRADE") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-100";
  if (rec === "MICRO_COATTAIL") return "border-sky-500/40 bg-sky-500/10 text-sky-100";
  if (rec === "WATCH") return "border-amber-500/35 bg-amber-500/10 text-amber-100";
  if (rec === "AVOID") return "border-rose-500/35 bg-rose-500/10 text-rose-100";
  return "border-border bg-surface/50 text-muted";
}

function fmtPct(v: unknown) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return `${n >= 0 ? "" : ""}${n.toFixed(1)}%`;
}

export function EarningsRecommendationCard({ rec }: { rec: Rec }) {
  const recommendation = String(rec.recommendation ?? "INSUFFICIENT_DATA");
  const direction = String(rec.direction ?? "no_directional_edge").replaceAll("_", " ");
  const alternatives = Array.isArray(rec.alternatives) ? (rec.alternatives as Rec[]) : [];
  const watching = Array.isArray(rec.watching) ? (rec.watching as string[]) : [];
  const targets = Array.isArray(rec.profit_targets) ? (rec.profit_targets as string[]) : [];

  return (
    <article className="rounded-xl border border-border bg-surface/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{String(rec.symbol)}</h3>
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${recTone(recommendation)}`}
            >
              {recommendation.replaceAll("_", " ")} — {direction}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            Phase {String(rec.phase ?? "—")} · Strategy {String(rec.strategy ?? "—").replaceAll("_", " ")}
          </p>
        </div>
        <DataStatusBadge status={String(rec.data_status ?? "simulated")} />
      </div>

      <p className="mt-3 text-sm text-foreground/90">{String(rec.summary ?? "")}</p>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted">Expected move</dt>
          <dd className="font-medium">±{fmtPct(rec.expected_move_pct).replace("%", "")}%</dd>
        </div>
        <div>
          <dt className="text-muted">Breakeven</dt>
          <dd className="font-medium">{fmtPct(rec.breakeven_pct)}</dd>
        </div>
        <div>
          <dt className="text-muted">Hist. avg move</dt>
          <dd className="font-medium">{fmtPct(rec.historical_avg_move_pct)}</dd>
        </div>
        <div>
          <dt className="text-muted">Est. IV crush</dt>
          <dd className="font-medium">{fmtPct(rec.estimated_iv_crush_pct)}</dd>
        </div>
        <div>
          <dt className="text-muted">Confidence</dt>
          <dd className="font-medium">{fmtPct(rec.confidence)}</dd>
        </div>
        <div>
          <dt className="text-muted">PoP</dt>
          <dd className="font-medium">{fmtPct(rec.probability_of_profit)}</dd>
        </div>
        <div>
          <dt className="text-muted">Expected value</dt>
          <dd className="font-medium">
            {rec.expected_value != null ? `$${Number(rec.expected_value).toFixed(2)}` : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Max risk</dt>
          <dd className="font-medium">
            {rec.max_loss != null ? `$${Number(rec.max_loss).toFixed(0)}` : "—"}
          </dd>
        </div>
      </dl>

      {rec.why_not_full_size ? (
        <p className="mt-3 text-xs text-amber-100/90">
          <span className="font-semibold">Why not full size:</span> {String(rec.why_not_full_size)}
        </p>
      ) : null}

      <p className="mt-2 text-xs text-muted">
        <span className="font-semibold text-foreground/80">Why this strategy:</span>{" "}
        {String(rec.why_strategy ?? "—")}
      </p>

      <details className="mt-3">
        <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-muted">
          Trade plan &amp; monitoring
        </summary>
        <ul className="mt-2 space-y-1 text-xs text-muted">
          <li>Entry: {String(rec.entry_condition ?? "—")}</li>
          <li>Invalidation: {String(rec.invalidation_condition ?? "—")}</li>
          <li>Holding: {String(rec.expected_holding_period ?? "—")}</li>
          <li>Suggested size: ${Number(rec.position_size_usd ?? rec.paper_position_size_usd ?? 0).toFixed(0)}</li>
          {targets.length > 0 && <li>Targets: {targets.join(" · ")}</li>}
          {rec.confirmation_condition && (
            <li>Confirmation: {String(rec.confirmation_condition)}</li>
          )}
          {rec.watch_expires_at && <li>Watch expires: {String(rec.watch_expires_at)}</li>}
          <li>Upgrade: {String(rec.upgrade_condition ?? "—")}</li>
          <li>Downgrade: {String(rec.downgrade_condition ?? "—")}</li>
          <li>Cancel: {String(rec.cancel_condition ?? "—")}</li>
        </ul>
        {watching.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs text-foreground/85">
            {watching.map((w) => (
              <li key={w}>◆ Watching: {w}</li>
            ))}
          </ul>
        )}
      </details>

      {alternatives.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-muted">
            Strategy comparison
          </summary>
          <ul className="mt-2 space-y-1.5 text-xs text-muted">
            {alternatives.slice(0, 6).map((a) => (
              <li key={`${String(a.strategy)}-${String(a.rank)}`}>
                <span className="font-medium text-foreground/85">
                  {String(a.strategy).replaceAll("_", " ")}
                </span>
                {a.rejected ? " · rejected" : " · ranked"}
                {a.expected_value != null ? ` · EV $${Number(a.expected_value).toFixed(2)}` : ""}
                {a.note ? ` — ${String(a.note)}` : ""}
                {a.reject_reason ? ` (${String(a.reject_reason)})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}
