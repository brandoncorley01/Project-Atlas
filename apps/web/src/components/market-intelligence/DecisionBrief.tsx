"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { DecisionAction, DecisionStance } from "@/lib/market-intelligence-decisions";
import { stanceToneClass } from "@/lib/market-intelligence-decisions";

function actionTone(tone?: DecisionAction["tone"]) {
  if (tone === "positive") return "border-emerald-500/35 bg-emerald-500/10 hover:bg-emerald-500/15";
  if (tone === "warning") return "border-amber-500/35 bg-amber-500/10 hover:bg-amber-500/15";
  if (tone === "danger") return "border-rose-500/35 bg-rose-500/10 hover:bg-rose-500/15";
  return "border-border bg-surface/60 hover:bg-surface-hover";
}

export function DecisionBrief({
  eyebrow,
  stance,
  actions,
  children,
}: {
  eyebrow: string;
  stance: DecisionStance;
  actions: DecisionAction[];
  children?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-sky-500/30 bg-gradient-to-br from-sky-500/10 via-transparent to-emerald-500/5 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/90">{eyebrow}</p>
          <h2 className="mt-1 text-lg font-semibold text-foreground">{stance.label}</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">{stance.detail}</p>
        </div>
        <span
          className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${stanceToneClass(stance.id)}`}
        >
          {stance.id.replaceAll("_", " ")}
        </span>
      </div>

      {actions.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-200/80">Do this next</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {actions.map((a) => {
              const className = `flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition ${actionTone(a.tone)}`;
              const body = (
                <>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground">{a.label}</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted">{a.reason}</p>
                  </div>
                  {a.href ? <span className="shrink-0 text-xs font-semibold text-sky-200">→</span> : null}
                </>
              );
              if (!a.href) {
                return (
                  <div key={`${a.label}-${a.reason}`} className={className}>
                    {body}
                  </div>
                );
              }
              if (a.href.startsWith("http") || a.href.startsWith("/")) {
                return (
                  <Link key={`${a.label}-${a.reason}`} href={a.href} className={className}>
                    {body}
                  </Link>
                );
              }
              return (
                <a key={`${a.label}-${a.reason}`} href={a.href} className={className}>
                  {body}
                </a>
              );
            })}
          </div>
        </div>
      )}

      {children}
    </section>
  );
}
