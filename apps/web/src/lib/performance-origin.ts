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
