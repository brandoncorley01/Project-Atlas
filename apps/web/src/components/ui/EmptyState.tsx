import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  compact?: boolean;
}

function DefaultIcon() {
  return (
    <svg
      className="mx-auto h-10 w-10 text-muted/50"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.25}
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 17v-2m3 2v-4m3 4v-6M5 21h14a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H5a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  );
}

export function EmptyState({ title, description, action, icon, compact }: EmptyStateProps) {
  return (
    <div
      className={`rounded-xl border border-dashed border-border bg-surface/40 text-center ${
        compact ? "px-6 py-8" : "px-8 py-12"
      }`}
    >
      <div className="mb-3">{icon ?? <DefaultIcon />}</div>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {description && (
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">{description}</p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
