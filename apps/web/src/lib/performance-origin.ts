/** Classify performance rows as Atlas picks vs user (watchlist/manual) picks. */

export type PickOrigin = "atlas" | "user" | "both";

type OriginEntry = {
  pick_origin?: string | null;
  resolution_source?: string | null;
  scoring_snapshot?: Record<string, unknown> | null;
};

export function resolvePickOrigin(entry: OriginEntry): PickOrigin {
  const snap = entry.scoring_snapshot ?? {};
  const userMarked = Boolean(
    snap.user_tracked || snap.watchlist_item_id || snap.user_entry || snap.source === "user_entry",
  );

  const stamped = entry.pick_origin;
  if (stamped === "atlas" || stamped === "user" || stamped === "both") {
    // Atlas board picks stay out of "my picks" unless the user also tracked them.
    if (stamped === "atlas" && !userMarked) return "atlas";
    if (stamped === "user") return "user";
    if (stamped === "both" || (stamped === "atlas" && userMarked)) return "both";
  }

  const snapOrigin = snap.pick_origin;
  if (snapOrigin === "atlas" || snapOrigin === "user" || snapOrigin === "both") {
    if (snapOrigin === "atlas" && !userMarked) return "atlas";
    if (snapOrigin === "user") return "user";
    if (snapOrigin === "both" || (snapOrigin === "atlas" && userMarked)) return "both";
  }

  if (snap.user_tracked && snap.atlas_tracked) return "both";
  if (userMarked) return "user";

  // Insight / odds scan board — learning only, not the user's waiting list.
  if (
    snap.atlas_presented ||
    snap.source === "openai_web" ||
    snap.source === "odds_scan" ||
    snap.source === "sports_scan"
  ) {
    return "atlas";
  }

  const src = String(entry.resolution_source ?? "");
  if (src === "watchlist" || src === "manual" || src === "manual_edit") return "user";
  return "atlas";
}

export function matchesOriginFilter(
  entry: OriginEntry,
  filter: "all" | "atlas" | "user",
): boolean {
  if (filter === "all") return true;
  const origin = resolvePickOrigin(entry);
  if (filter === "atlas") return origin === "atlas" || origin === "both";
  return origin === "user" || origin === "both";
}

export function originLabel(origin: PickOrigin): string {
  if (origin === "user") return "Your pick";
  if (origin === "both") return "Atlas + yours";
  return "Atlas pick";
}

/** Watchlist saves and manual logs — includes picks you saved from Atlas scans. */
export function isUserLane(entry: OriginEntry): boolean {
  const origin = resolvePickOrigin(entry);
  return origin === "user" || origin === "both";
}

/** Auto-tracked scan picks only (excludes watchlist saves to avoid duplicate rows). */
export function isAtlasOnlyLane(entry: OriginEntry): boolean {
  return resolvePickOrigin(entry) === "atlas";
}

export function groupBySector<T extends { module: string }>(
  rows: T[],
): Record<"sports" | "stock" | "options" | "parlay", T[]> {
  const grouped = {
    sports: [] as T[],
    stock: [] as T[],
    options: [] as T[],
    parlay: [] as T[],
  };
  for (const row of rows) {
    const mod = row.module as keyof typeof grouped;
    if (grouped[mod]) grouped[mod].push(row);
  }
  for (const key of Object.keys(grouped) as (keyof typeof grouped)[]) {
    grouped[key].sort((a, b) => {
      const aRow = a as { outcome?: string; logged_at?: string };
      const bRow = b as { outcome?: string; logged_at?: string };
      const ap = aRow.outcome === "pending" ? 0 : 1;
      const bp = bRow.outcome === "pending" ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return String(bRow.logged_at ?? "").localeCompare(String(aRow.logged_at ?? ""));
    });
  }
  return grouped;
}

/** Pending rows only — the default "waiting to be graded" list. */
export function pendingOnly<T extends { outcome?: string }>(rows: T[]): T[] {
  return rows.filter((r) => r.outcome === "pending");
}

/** Settled / graded rows. */
export function gradedOnly<T extends { outcome?: string }>(rows: T[]): T[] {
  return rows.filter((r) => ["win", "loss", "scratch"].includes(String(r.outcome ?? "")));
}
