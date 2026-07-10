/** Classify performance rows as Atlas picks vs user (watchlist/manual) picks. */

export type PickOrigin = "atlas" | "user" | "both";

export function resolvePickOrigin(entry: {
  pick_origin?: string | null;
  resolution_source?: string | null;
  scoring_snapshot?: Record<string, unknown> | null;
}): PickOrigin {
  const stamped = entry.pick_origin;
  if (stamped === "atlas" || stamped === "user" || stamped === "both") {
    return stamped;
  }
  const snap = entry.scoring_snapshot ?? {};
  const snapOrigin = snap.pick_origin;
  if (snapOrigin === "atlas" || snapOrigin === "user" || snapOrigin === "both") {
    return snapOrigin;
  }
  if (snap.user_tracked && snap.atlas_tracked) return "both";
  if (snap.user_tracked || snap.watchlist_item_id) return "user";

  const src = String(entry.resolution_source ?? "");
  if (src === "watchlist" || src === "manual" || src === "manual_edit") return "user";
  return "atlas";
}

export function matchesOriginFilter(
  entry: { pick_origin?: string | null; resolution_source?: string | null },
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
export function isUserLane(
  entry: { pick_origin?: string | null; resolution_source?: string | null },
): boolean {
  const origin = resolvePickOrigin(entry);
  return origin === "user" || origin === "both";
}

/** Auto-tracked scan picks only (excludes watchlist saves to avoid duplicate rows). */
export function isAtlasOnlyLane(
  entry: { pick_origin?: string | null; resolution_source?: string | null },
): boolean {
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
