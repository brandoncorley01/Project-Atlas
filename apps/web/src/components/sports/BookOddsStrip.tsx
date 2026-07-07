"use client";

export interface BookOddsLine {
  key: string;
  title: string;
  american: number;
  decimal?: number;
  is_primary?: boolean;
}

interface BookOddsStripProps {
  books: BookOddsLine[];
  preferredBook?: string;
  compact?: boolean;
}

function formatAmerican(american: number) {
  return american > 0 ? `+${american}` : `${american}`;
}

export function BookOddsStrip({ books, preferredBook = "fanduel", compact }: BookOddsStripProps) {
  if (!books.length) return null;

  const sorted = [...books].sort((a, b) => {
    if (a.key === preferredBook) return -1;
    if (b.key === preferredBook) return 1;
    return a.title.localeCompare(b.title);
  });

  return (
    <div className={compact ? "mt-2" : "mt-3"}>
      {!compact && (
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
          Odds by sportsbook · FanDuel is your play line
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {sorted.map((book) => {
          const isPrimary = book.key === preferredBook || book.is_primary;
          return (
            <div
              key={book.key}
              className={`rounded-lg border px-2.5 py-1.5 ${
                isPrimary
                  ? "border-fanduel/50 bg-fanduel-muted ring-1 ring-fanduel/30"
                  : "border-border bg-background/60"
              }`}
            >
              <p
                className={`text-[10px] font-semibold uppercase tracking-wide ${
                  isPrimary ? "text-fanduel-text" : "text-muted"
                }`}
              >
                {book.title}
                {isPrimary && " · Play"}
              </p>
              <p className={`text-sm font-bold ${isPrimary ? "text-foreground" : "text-muted-foreground"}`}>
                {formatAmerican(book.american)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
