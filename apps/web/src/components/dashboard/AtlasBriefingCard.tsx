"use client";

import { useState } from "react";

export interface AtlasBriefing {
  headline?: string;
  summary?: string;
  highlights?: string[];
  watch_items?: string[];
  learning_insight?: string | null;
  generated_at?: string;
  source?: "openai" | "template" | string;
  model?: string | null;
}

interface AtlasBriefingCardProps {
  briefing?: AtlasBriefing | null;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function AtlasBriefingCard({ briefing, onRefresh, refreshing }: AtlasBriefingCardProps) {
  const [expanded, setExpanded] = useState(true);

  if (!briefing?.headline && !briefing?.summary) {
    return null;
  }

  const isAi = briefing.source === "openai";

  return (
    <section className="mb-8 overflow-hidden rounded-xl border border-sky-500/30 bg-gradient-to-br from-sky-500/10 via-violet-500/5 to-transparent">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-sky-500/20 px-4 py-3 sm:px-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg" aria-hidden>
              ✦
            </span>
            <h2 className="text-sm font-semibold tracking-wide text-sky-100">Atlas briefing</h2>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                isAi
                  ? "bg-sky-500/20 text-sky-200"
                  : "bg-surface text-muted"
              }`}
            >
              {isAi ? "AI" : "Smart summary"}
            </span>
          </div>
          <p className="mt-1 text-base font-medium text-foreground">{briefing.headline}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="rounded-lg border border-sky-500/30 px-2.5 py-1 text-xs font-medium text-sky-200 hover:bg-sky-500/10 disabled:opacity-50"
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted hover:bg-surface-hover"
            aria-expanded={expanded}
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="space-y-4 px-4 py-4 sm:px-5">
          {briefing.summary && (
            <p className="text-sm leading-relaxed text-muted">{briefing.summary}</p>
          )}

          {briefing.highlights && briefing.highlights.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">
                Today&apos;s highlights
              </h3>
              <ul className="mt-2 space-y-1.5">
                {briefing.highlights.map((item) => (
                  <li key={item} className="flex gap-2 text-sm text-foreground/90">
                    <span className="text-sky-400" aria-hidden>
                      →
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {briefing.watch_items && briefing.watch_items.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-200/80">
                Action items
              </h3>
              <ul className="mt-2 space-y-1.5">
                {briefing.watch_items.map((item) => (
                  <li key={item} className="text-sm text-muted">
                    · {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {briefing.learning_insight && (
            <p className="rounded-lg border border-violet-500/25 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">
              <span className="font-medium">Learning: </span>
              {briefing.learning_insight}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
