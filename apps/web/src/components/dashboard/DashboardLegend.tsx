"use client";

import { useState } from "react";
import { GLOSSARY } from "@/lib/glossary";
import { TermHint } from "@/components/ui/TermHint";

interface LegendItemProps {
  swatch?: string;
  label: string;
  description: string;
}

function LegendItem({ swatch, label, description }: LegendItemProps) {
  return (
    <div className="flex gap-3">
      {swatch && (
        <span
          className={`mt-0.5 h-4 w-4 shrink-0 rounded-md border border-border ${swatch}`}
          aria-hidden
        />
      )}
      <div>
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="text-xs leading-relaxed text-muted">{description}</p>
      </div>
    </div>
  );
}

function ScoreScale() {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="rounded-full bg-success/20 px-2 py-0.5 font-semibold text-success">75+ Strong</span>
      <span className="rounded-full bg-warning/20 px-2 py-0.5 font-semibold text-warning">50–74 OK</span>
      <span className="rounded-full bg-background px-2 py-0.5 font-medium text-muted">&lt;50 Weak</span>
    </div>
  );
}

export function DashboardLegend() {
  const [open, setOpen] = useState(true);

  return (
    <section className="atlas-card mb-8 border-accent/20 bg-gradient-to-br from-surface to-accent-muted/30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
        aria-expanded={open}
      >
        <div>
          <h2 className="text-base font-bold text-foreground">📖 Dashboard legend</h2>
          <p className="mt-0.5 text-xs text-muted">
            What the scores, colors, and badges mean — hover dotted terms anywhere for quick definitions.
          </p>
        </div>
        <span className="shrink-0 text-sm text-muted">{open ? "Hide ▲" : "Show ▼"}</span>
      </button>

      {open && (
        <div className="grid gap-6 border-t border-border/60 px-5 pb-5 pt-4 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-accent">Score badges</h3>
            <LegendItem
              label="Confidence"
              description={GLOSSARY.confidence}
            />
            <LegendItem
              label="Risk"
              description={`${GLOSSARY.risk} For risk, lower numbers are better.`}
            />
            <LegendItem
              label="Opportunity"
              description={`${GLOSSARY.opportunity} Sort by this to find the best overall pick.`}
            />
            <ScoreScale />
          </div>

          <div className="space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-violet-400">Sports (24/7)</h3>
            <LegendItem
              swatch="bg-fanduel-muted border-fanduel/40"
              label="FanDuel line (blue)"
              description="Your play line — the odds Atlas recommends you take at FanDuel."
            />
            <LegendItem
              swatch="bg-success/20"
              label="EV +X% (green)"
              description={GLOSSARY.ev}
            />
            <LegendItem
              label="Edge %"
              description={GLOSSARY.edge}
            />
            <LegendItem
              swatch="bg-sky-500/20"
              label="Steam move"
              description={GLOSSARY.steam}
            />
            <p className="text-xs text-muted">
              <TermHint term="parlay" /> — build tickets on the Parlays page after scanning sports.
            </p>
          </div>

          <div className="space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-sky-400">Options & stocks</h3>
            <LegendItem
              swatch="bg-gradient-to-r from-emerald-500/30 to-cyan-500/30"
              label="Under $100 tag"
              description="Options contract costs $100 or less to open one position."
            />
            <LegendItem
              swatch="bg-amber-500/20"
              label="News catalyst"
              description={GLOSSARY.catalyst}
            />
            <LegendItem
              label="RSI / MACD"
              description={`${GLOSSARY.rsi} ${GLOSSARY.macd}`}
            />
            <LegendItem
              swatch="bg-success/20"
              label="Win probability"
              description="Estimated chance the options trade is profitable at expiration."
            />
          </div>
        </div>
      )}
    </section>
  );
}
