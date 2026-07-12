"use client";

import Link from "next/link";

export interface FilterSelectItem {
  id: string;
  label: string;
  count?: number;
  description?: string;
}

interface FilterSelectProps {
  label: string;
  hint?: string;
  allLabel?: string;
  items: FilterSelectItem[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  guideLinks?: { href: string; label: string }[];
}

export function FilterSelect({
  label,
  hint,
  allLabel = "All",
  items,
  activeId,
  onSelect,
  guideLinks,
}: FilterSelectProps) {
  const active = items.find((i) => i.id === activeId);
  const activeGuide = activeId
    ? guideLinks?.find((g) => g.href.endsWith(`/${activeId}`) || g.href.includes(`/${activeId}`))
    : null;

  return (
    <div className="mb-0 sm:mb-0">
      <label className="flex flex-col gap-1 text-xs text-muted">
        <span className="font-semibold uppercase tracking-wider">{label}</span>
        {hint && <span className="font-normal normal-case tracking-normal text-muted/90">{hint}</span>}
        <select
          value={activeId ?? ""}
          onChange={(e) => onSelect(e.target.value ? e.target.value : null)}
          aria-label={label}
          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-violet-500"
        >
          <option value="">{allLabel}</option>
          {items.map((item) => (
            <option key={item.id} value={item.id} title={item.description}>
              {item.label}
              {item.count != null && item.count > 0 ? ` (${item.count})` : ""}
            </option>
          ))}
        </select>
      </label>

      {active?.description && (
        <p className="mt-2 text-xs text-muted">{active.description}</p>
      )}

      {activeGuide && (
        <Link
          href={activeGuide.href}
          className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
        >
          {activeGuide.label}
        </Link>
      )}
    </div>
  );
}
