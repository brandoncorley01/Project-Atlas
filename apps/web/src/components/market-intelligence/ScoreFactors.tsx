"use client";

/** Human-readable score factors — never dump raw JSON to the user. */
export function ScoreFactors({
  title = "What’s driving this",
  positives = [],
  negatives = [],
  components,
}: {
  title?: string;
  positives?: string[];
  negatives?: string[];
  components?: Record<string, number>;
}) {
  const entries = Object.entries(components ?? {});
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
      {entries.length > 0 && (
        <div className="space-y-2">
          {entries.map(([key, value]) => (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="capitalize text-muted">{key.replaceAll("_", " ")}</span>
                <span className="font-medium text-foreground">{Math.round(value)}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-background">
                <div
                  className="h-full rounded-full bg-accent/70"
                  style={{ width: `${Math.max(4, Math.min(100, value))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <FactorList heading="Supporting" items={positives} tone="good" />
        <FactorList heading="Watch / caution" items={negatives} tone="warn" />
      </div>
    </div>
  );
}

function FactorList({
  heading,
  items,
  tone,
}: {
  heading: string;
  items: string[];
  tone: "good" | "warn";
}) {
  const color = tone === "good" ? "text-emerald-300" : "text-amber-200";
  return (
    <div>
      <p className={`text-xs font-semibold ${color}`}>{heading}</p>
      <ul className="mt-1 space-y-1 text-sm text-muted">
        {items.length === 0 && <li>—</li>}
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}
