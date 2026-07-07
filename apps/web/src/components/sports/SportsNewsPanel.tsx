function ExternalLinkIcon() {
  return (
    <svg className="inline h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

function formatTime(iso?: string | null) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return null;
  }
}

export interface SportsNewsItem {
  title: string;
  url?: string | null;
  source?: string | null;
  summary?: string | null;
  published_at?: string | null;
  relevance_score?: number;
  matched_tokens?: string[];
}

export function SportsNewsPanel({
  items,
  analysisSummary,
  verified = false,
}: {
  items: SportsNewsItem[];
  analysisSummary?: string | null;
  verified?: boolean;
}) {
  if (!items.length && !analysisSummary) return null;

  return (
    <div className="rounded-xl border border-sky-500/35 bg-gradient-to-br from-sky-500/10 to-surface p-4">
      <p className="text-xs font-bold uppercase tracking-wider text-sky-300">
        {verified ? "📰 Verified news for this matchup" : "📰 News context"}
      </p>
      {verified && (
        <p className="mt-1 text-xs text-muted">
          Headlines must name the team or mascot — city-only mentions do not count.
        </p>
      )}

      {analysisSummary && (
        <p className="mt-3 text-sm leading-relaxed text-foreground">{analysisSummary}</p>
      )}

      {items.length > 0 && (
        <ul className="mt-3 space-y-3">
          {items.map((item, idx) => (
            <li
              key={`${item.title}-${idx}`}
              className="rounded-lg border border-border/60 bg-background/40 p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h4 className="text-sm font-semibold leading-snug">
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-start gap-1.5 text-accent hover:underline"
                    >
                      {item.title}
                      <ExternalLinkIcon />
                    </a>
                  ) : (
                    item.title
                  )}
                </h4>
                {item.url && item.source && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="shrink-0 rounded-md border border-accent/30 bg-accent/10 px-2 py-1 text-[10px] font-semibold text-accent hover:bg-accent/20"
                  >
                    {item.source} ↗
                  </a>
                )}
              </div>
              <p className="mt-1 text-xs text-muted">
                {item.source}
                {formatTime(item.published_at) && ` · ${formatTime(item.published_at)}`}
                {item.relevance_score != null && ` · ${item.relevance_score}% relevance`}
                {item.matched_tokens?.length ? ` · matched: ${item.matched_tokens.join(", ")}` : ""}
              </p>
              {item.summary && (
                <p className="mt-1.5 text-xs leading-relaxed text-muted line-clamp-2">{item.summary}</p>
              )}
              {item.url && (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-xs font-semibold text-accent hover:underline"
                >
                  Read full story →
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
