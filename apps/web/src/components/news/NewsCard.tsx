import Link from "next/link";
import { TermHint } from "@/components/ui/TermHint";

export interface AffectedCompany {
  symbol: string;
  price?: number | null;
  change?: number | null;
  change_pct?: number | null;
}

export interface NewsItem {
  id: string;
  source: string;
  title: string;
  url?: string | null;
  summary?: string | null;
  published_at?: string | null;
  sentiment: string;
  impact_score: number;
  time_sensitivity_score: number;
  explanation?: string | null;
  related_tickers: string[];
  affected_companies?: AffectedCompany[];
}

const SENTIMENT_STYLES: Record<string, { pill: string; label: string }> = {
  bullish: {
    pill: "bg-success/20 text-success border-success/40",
    label: "📈 Bullish",
  },
  bearish: {
    pill: "bg-danger/20 text-danger border-danger/40",
    label: "📉 Bearish",
  },
  neutral: {
    pill: "bg-background text-muted border-border",
    label: "➖ Neutral",
  },
};

function formatPublished(iso?: string | null) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diffH = (now - d.getTime()) / 3_600_000;
    if (diffH < 1) return "Just now";
    if (diffH < 24) return `${Math.floor(diffH)}h ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return null;
  }
}

function ExternalLinkIcon() {
  return (
    <svg className="inline h-3.5 w-3.5 shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

function AffectedCompaniesBar({
  companies,
  compact,
}: {
  companies: AffectedCompany[];
  compact?: boolean;
}) {
  if (companies.length === 0) {
    return (
      <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 px-3 py-2">
        <p className="text-xs font-medium text-amber-200/90">Market-wide headline</p>
        <p className="mt-0.5 text-xs text-muted">No single stock ticker linked</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/8 px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300/90">
        Stocks affected
      </p>
      <div className={`mt-2 flex flex-wrap gap-2 ${compact ? "gap-1.5" : ""}`}>
        {companies.map((co) => {
          const pct = co.change_pct ?? 0;
          const up = pct > 0;
          const down = pct < 0;
          const changeClass = up ? "text-success" : down ? "text-danger" : "text-muted";

          return (
            <Link
              key={co.symbol}
              href={`/stocks?symbol=${encodeURIComponent(co.symbol)}`}
              className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/10"
              title={`View ${co.symbol} signals`}
            >
              <span className="text-sm font-bold text-foreground">{co.symbol}</span>
              {co.price != null ? (
                <>
                  <span className="text-sm font-medium">${Number(co.price).toFixed(2)}</span>
                  <span className={`text-xs font-semibold ${changeClass}`}>
                    {up ? "+" : ""}
                    {Number(pct).toFixed(2)}%
                  </span>
                </>
              ) : (
                <span className="text-xs text-muted">tap to explore →</span>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function NewsCard({ item, compact }: { item: NewsItem; compact?: boolean }) {
  const sentiment = SENTIMENT_STYLES[item.sentiment] ?? SENTIMENT_STYLES.neutral;
  const companies =
    item.affected_companies ??
    item.related_tickers.map((symbol) => ({ symbol, price: null, change: null, change_pct: null }));
  const published = formatPublished(item.published_at);
  const hasUrl = Boolean(item.url);

  return (
    <article
      className={`atlas-card atlas-card-interactive p-4 sm:p-5 ${
        item.time_sensitivity_score >= 60 ? "border-amber-500/30 ring-1 ring-amber-500/15" : ""
      }`}
    >
      <AffectedCompaniesBar companies={companies} compact={compact} />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${sentiment.pill}`}>
            {sentiment.label}
          </span>
          <span
            className="rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-200"
            title="How much this news could move prices (0–100)"
          >
            <TermHint term="impact" label={`Impact ${Math.round(item.impact_score)}`} className="text-amber-200" />
          </span>
          {item.time_sensitivity_score >= 60 && (
            <span className="rounded-full bg-danger/20 px-2.5 py-0.5 text-xs font-bold text-danger animate-pulse">
              🔴 Breaking
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          {published && <time>{published}</time>}
          {hasUrl ? (
            <a
              href={item.url!}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-accent/30 bg-accent/10 px-2 py-1 font-semibold text-accent hover:bg-accent/20"
            >
              Read on {item.source}
              <ExternalLinkIcon />
            </a>
          ) : (
            <span className="font-medium">{item.source}</span>
          )}
        </div>
      </div>

      <h3 className="mt-3 text-base font-bold leading-snug sm:text-lg">
        {hasUrl ? (
          <a
            href={item.url!}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-start gap-2 text-foreground hover:text-accent"
          >
            <span>{item.title}</span>
            <ExternalLinkIcon />
          </a>
        ) : (
          item.title
        )}
      </h3>

      {(item.summary || !compact) && item.summary && (
        <p className="mt-2 text-sm leading-relaxed text-muted line-clamp-3">{item.summary}</p>
      )}

      {!compact && item.explanation && (
        <div className="mt-3 rounded-lg border border-sky-500/25 bg-sky-500/8 px-3 py-2">
          <p className="text-xs font-semibold text-sky-300">Why this matters</p>
          <p className="mt-1 text-sm leading-relaxed text-foreground/90">{item.explanation}</p>
        </div>
      )}

      {hasUrl && (
        <a
          href={item.url!}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent/90"
        >
          Read full article at {item.source}
          <ExternalLinkIcon />
        </a>
      )}
    </article>
  );
}
