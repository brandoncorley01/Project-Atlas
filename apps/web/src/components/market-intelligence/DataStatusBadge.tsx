"use client";

import type { Freshness } from "@/lib/market-intelligence-api";

const STATUS_STYLES: Record<string, string> = {
  live: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  delayed: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  cached: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  historical: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  simulated: "bg-rose-500/15 text-rose-200 border-rose-500/30",
  partial: "bg-orange-500/15 text-orange-200 border-orange-500/30",
};

export function DataStatusBadge({
  status,
  freshness,
}: {
  status?: string | null;
  freshness?: Freshness | null;
}) {
  const value = (status || freshness?.data_status || "partial").toLowerCase();
  const style = STATUS_STYLES[value] || STATUS_STYLES.partial;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style}`}
      title={
        freshness?.data_timestamp
          ? `Data as of ${freshness.data_timestamp} · ${freshness.provider_name ?? ""}`
          : freshness?.provider_name
      }
    >
      <span aria-hidden>{value === "simulated" ? "◇" : value === "live" ? "●" : "○"}</span>
      {value}
      {freshness?.data_freshness ? ` · ${freshness.data_freshness}` : ""}
    </span>
  );
}

export function FreshnessLine({ freshness }: { freshness?: Freshness | null }) {
  if (!freshness) return null;
  return (
    <p className="text-xs text-muted">
      Provider: {freshness.provider_name ?? "—"}
      {freshness.data_timestamp ? ` · as of ${new Date(freshness.data_timestamp).toLocaleString()}` : ""}
      {freshness.evaluation_timestamp
        ? ` · evaluated ${new Date(freshness.evaluation_timestamp).toLocaleString()}`
        : ""}
    </p>
  );
}
