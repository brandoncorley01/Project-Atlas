import type { ReactNode } from "react";
import Link from "next/link";

interface SectionHeaderProps {
  title: string;
  description?: string;
  href?: string;
  linkLabel?: string;
  count?: number;
}

export function SectionHeader({
  title,
  description,
  href,
  linkLabel = "View all →",
  count,
}: SectionHeaderProps) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h2>
          {count != null && count > 0 && (
            <span className="rounded-full bg-accent-muted px-2 py-0.5 text-[10px] font-medium text-accent">
              {count}
            </span>
          )}
        </div>
        {description && <p className="mt-1 text-xs leading-relaxed text-muted/90">{description}</p>}
      </div>
      {href && (
        <Link href={href} className="text-xs font-medium text-accent hover:underline">
          {linkLabel}
        </Link>
      )}
    </div>
  );
}
