"use client";

import Link from "next/link";

export type TabAccent = "violet" | "orange" | "emerald" | "sky" | "amber" | "accent";

const accentActive: Record<TabAccent, string> = {
  violet: "bg-violet-600 text-white shadow-md shadow-violet-600/25",
  orange: "bg-orange-500 text-white shadow-md shadow-orange-500/25",
  emerald: "bg-emerald-600 text-white shadow-md shadow-emerald-600/25",
  sky: "bg-sky-600 text-white shadow-md shadow-sky-600/25",
  amber: "bg-amber-500 text-white shadow-md shadow-amber-500/25",
  accent: "bg-accent text-white shadow-md shadow-accent/25",
};

const accentRing: Record<TabAccent, string> = {
  violet: "ring-violet-500/40",
  orange: "ring-orange-500/40",
  emerald: "ring-emerald-500/40",
  sky: "ring-sky-500/40",
  amber: "ring-amber-500/40",
  accent: "ring-accent/40",
};

export interface FilterTabItem {
  id: string;
  label: string;
  count?: number;
  description?: string;
}

interface FilterTabsProps {
  label: string;
  hint?: string;
  allLabel?: string;
  items: FilterTabItem[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  accent?: TabAccent;
  guideLinks?: { href: string; label: string }[];
}

export function FilterTabs({
  label,
  hint,
  allLabel = "All",
  items,
  activeId,
  onSelect,
  accent = "accent",
  guideLinks,
}: FilterTabsProps) {
  const inactive =
    "border border-border bg-surface-elevated text-muted hover:border-accent/40 hover:text-foreground";

  return (
    <div className="mb-6">
      <div className="mb-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
        {hint && <p className="mt-1 text-xs leading-relaxed text-muted/90">{hint}</p>}
      </div>

      <div
        role="tablist"
        aria-label={label}
        className="flex flex-wrap gap-2"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeId === null}
          onClick={() => onSelect(null)}
          className={`rounded-full px-3.5 py-2 text-xs font-semibold transition-all ${
            activeId === null ? accentActive[accent] : inactive
          }`}
        >
          {allLabel}
        </button>
        {items.map((item) => {
          const selected = activeId === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              title={item.description}
              onClick={() => onSelect(item.id)}
              className={`rounded-full px-3.5 py-2 text-xs font-semibold transition-all ${
                selected
                  ? `${accentActive[accent]} ring-2 ${accentRing[accent]}`
                  : inactive
              }`}
            >
              {item.label}
              {item.count != null && item.count > 0 && (
                <span className="ml-1 opacity-80">({item.count})</span>
              )}
            </button>
          );
        })}
      </div>

      {guideLinks && guideLinks.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {guideLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="font-medium text-accent hover:underline"
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
