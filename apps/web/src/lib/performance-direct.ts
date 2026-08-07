import { createClient } from "@/lib/supabase/client";
import type { PerformanceEntry, PerformanceSummary } from "@/components/performance/PerformanceView";
import {
  effectiveItemType,
  normalizeWatchlistItem,
  normalizeWatchlistSymbol,
  performanceTrackingForItem,
  type WatchlistItem,
} from "@/lib/watchlist-types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function normalizeSignalId(signalId: string): string {
  const trimmed = signalId.trim();
  return UUID_RE.test(trimmed) ? trimmed.toLowerCase() : trimmed;
}

function isUuid(signalId: string): boolean {
  return UUID_RE.test(signalId.trim());
}

function formatRow(row: Record<string, unknown>): PerformanceEntry {
  const snap =
    row.scoring_snapshot && typeof row.scoring_snapshot === "object"
      ? (row.scoring_snapshot as Record<string, unknown>)
      : {};
  const stamped = snap.pick_origin;
  let pick_origin: "atlas" | "user" | "both" = "atlas";
  if (stamped === "atlas" || stamped === "user" || stamped === "both") {
    pick_origin = stamped;
  } else if (snap.user_tracked || snap.watchlist_item_id) {
    pick_origin = snap.atlas_tracked ? "both" : "user";
  } else {
    const src = String(row.resolution_source ?? "");
    if (src === "watchlist" || src === "manual" || src === "manual_edit") {
      pick_origin = "user";
    }
  }
  return {
    id: String(row.id),
    module: String(row.module),
    signal_id: String(row.signal_id),
    outcome: String(row.outcome),
    return_pct: row.return_pct != null ? Number(row.return_pct) : null,
    hold_duration_hours:
      row.hold_duration_hours != null ? Number(row.hold_duration_hours) : null,
    logged_at: typeof row.logged_at === "string" ? row.logged_at : undefined,
    resolution_source:
      typeof row.resolution_source === "string" ? row.resolution_source : null,
    signal_label: typeof row.signal_label === "string" ? row.signal_label : null,
    pick_origin,
    graded_by: typeof snap.graded_by === "string" ? snap.graded_by : null,
    leg_outcomes: Array.isArray(snap.leg_outcomes)
      ? (snap.leg_outcomes as NonNullable<PerformanceEntry["leg_outcomes"]>)
      : null,
    scoring_snapshot: snap,
  };
}

function signalLabel(
  module: string,
  snap: Record<string, unknown>,
): string | null {
  if (typeof snap.label === "string") return snap.label;
  if (module === "sports") {
    return `${snap.sport ?? ""} · ${snap.selection ?? ""}`.trim();
  }
  if (module === "stock") {
    return String(snap.symbol ?? snap.ticker ?? snap.recommendation ?? "");
  }
  if (module === "options") {
    return `${snap.underlying ?? ""} ${snap.option_type ?? ""} ${snap.strike ?? ""}`.trim();
  }
  if (module === "parlay") {
    return String(snap.name ?? snap.title ?? snap.style ?? "Parlay");
  }
  return null;
}

async function getSession() {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  return {
    supabase,
    userId: data.session?.user?.id ?? null,
    email: data.session?.user?.email ?? "",
  };
}

async function ensureProfile(
  supabase: ReturnType<typeof createClient>,
  userId: string,
  email: string,
): Promise<void> {
  const { data } = await supabase.from("profiles").select("id").eq("id", userId).maybeSingle();
  if (data?.id) return;
  await supabase.from("profiles").insert({ id: userId, email });
}

export function computeSummaryDirect(
  rows: PerformanceEntry[],
  days = 30,
  includeByModule = true,
): PerformanceSummary {
  const closed = rows.filter((r) => ["win", "loss", "scratch"].includes(r.outcome));
  const wins = closed.filter((r) => r.outcome === "win");
  const losses = closed.filter((r) => r.outcome === "loss");
  const scratches = closed.filter((r) => r.outcome === "scratch");
  const pending = rows.filter((r) => r.outcome === "pending");

  const winReturns = wins
    .map((r) => r.return_pct)
    .filter((v): v is number => v != null);
  const lossReturns = losses
    .map((r) => r.return_pct)
    .filter((v): v is number => v != null);

  const decided = wins.length + losses.length;
  const winRate = decided > 0 ? Math.round((wins.length / decided) * 1000) / 10 : null;

  const by_module: Record<string, PerformanceSummary> = {};
  if (includeByModule) {
    const modules = ["sports", "stock", "options", "parlay"] as const;
    for (const mod of modules) {
      const modRows = rows.filter((r) => r.module === mod);
      if (modRows.length > 0) {
        // Leaf summaries only — never nest by_module again (avoids infinite recursion).
        by_module[mod] = computeSummaryDirect(modRows, days, false);
      }
    }
  }

  const autoResolved = closed.filter((r) =>
    String(r.resolution_source ?? "").startsWith("auto_"),
  ).length;

  return {
    days,
    total_signals: closed.length,
    wins: wins.length,
    losses: losses.length,
    scratches: scratches.length,
    pending: pending.length,
    win_rate: winRate,
    avg_return_pct:
      winReturns.length > 0
        ? Math.round((winReturns.reduce((a, b) => a + b, 0) / winReturns.length) * 100) / 100
        : null,
    avg_loss_pct:
      lossReturns.length > 0
        ? Math.round((lossReturns.reduce((a, b) => a + b, 0) / lossReturns.length) * 100) / 100
        : null,
    auto_resolved: autoResolved,
    by_module,
    learning_active: closed.length >= 8,
    learning_notes:
      closed.length >= 8
        ? ["Atlas is adjusting thresholds from your logged results."]
        : [],
  };
}

export async function fetchPerformanceHistoryDirect(
  limit = 200,
): Promise<PerformanceEntry[]> {
  const { supabase, userId } = await getSession();
  if (!userId) return [];

  const { data, error } = await supabase
    .from("signal_performance")
    .select(
      "id, module, signal_id, outcome, return_pct, hold_duration_hours, logged_at, resolution_source, signal_label, scoring_snapshot",
    )
    .eq("user_id", userId)
    .order("logged_at", { ascending: false })
    .limit(limit);

  if (error || !data) return [];
  return data.map((row) => formatRow(row as Record<string, unknown>));
}

export async function getOutcomeDirect(
  module: string,
  signalId: string,
): Promise<PerformanceEntry | null> {
  const { supabase, userId } = await getSession();
  if (!userId) return null;
  const sid = normalizeSignalId(signalId);

  const { data, error } = await supabase
    .from("signal_performance")
    .select(
      "id, module, signal_id, outcome, return_pct, hold_duration_hours, logged_at, resolution_source, signal_label, scoring_snapshot",
    )
    .eq("user_id", userId)
    .eq("module", module)
    .eq("signal_id", sid)
    .maybeSingle();

  if (error || !data) return null;
  return formatRow(data as Record<string, unknown>);
}

export async function logOutcomeDirect(params: {
  module: string;
  signalId: string;
  outcome: string;
  returnPct?: number | null;
  holdDurationHours?: number | null;
  resolutionSource?: string;
  signalSnapshot?: Record<string, unknown>;
}): Promise<PerformanceEntry | null> {
  const { supabase, userId, email } = await getSession();
  if (!userId) return null;

  const signalId = normalizeSignalId(params.signalId);
  if (!isUuid(signalId)) {
    throw new Error("Invalid signal id — save this pick to your watchlist first.");
  }

  await ensureProfile(supabase, userId, email);

  const existing = await getOutcomeDirect(params.module, params.signalId);
  if (
    existing &&
    params.outcome === "pending" &&
    ["win", "loss", "scratch"].includes(existing.outcome)
  ) {
    // Don't downgrade graded picks — but still stamp user origin if watchlist sync.
    if (params.resolutionSource === "watchlist") {
      const { supabase: sb } = await getSession();
      const existingSnap = existing.scoring_snapshot ?? {};
      const snap = {
        ...existingSnap,
        ...(params.signalSnapshot ?? {}),
        pick_origin:
          existingSnap.pick_origin === "atlas" || existingSnap.pick_origin === "both"
            ? "both"
            : "user",
        user_tracked: true,
      };
      await sb
        .from("signal_performance")
        .update({
          resolution_source: "watchlist",
          scoring_snapshot: snap,
          updated_at: new Date().toISOString(),
        })
        .eq("id", existing.id);
      return {
        ...existing,
        resolution_source: "watchlist",
        pick_origin: snap.pick_origin as "user" | "both",
        scoring_snapshot: snap,
      };
    }
    return existing;
  }
  if (
    existing &&
    params.outcome === "pending" &&
    existing.outcome === "pending" &&
    params.resolutionSource !== "watchlist"
  ) {
    return existing;
  }

  const now = new Date().toISOString();
  const existingSnap =
    existing?.scoring_snapshot && typeof existing.scoring_snapshot === "object"
      ? { ...existing.scoring_snapshot }
      : {};
  const incoming = { ...(params.signalSnapshot ?? {}) };
  // Nested scoring_snapshot payloads should flatten into the stored snap.
  const nested = incoming.scoring_snapshot;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    Object.assign(incoming, nested as Record<string, unknown>);
    delete incoming.scoring_snapshot;
  }
  const snap: Record<string, unknown> = { ...existingSnap };
  for (const [k, v] of Object.entries(incoming)) {
    if (v != null) snap[k] = v;
  }
  const src = params.resolutionSource ?? "manual";
  if (src === "watchlist" || src === "manual" || src === "manual_edit") {
    snap.pick_origin =
      snap.pick_origin === "atlas" || snap.pick_origin === "both" ? "both" : "user";
    snap.user_tracked = true;
  } else if (src === "auto_scan" || String(src).startsWith("auto_")) {
    snap.pick_origin =
      snap.pick_origin === "user" || snap.pick_origin === "both" ? "both" : "atlas";
    snap.atlas_tracked = true;
  }
  const row: Record<string, unknown> = {
    user_id: userId,
    module: params.module,
    signal_id: signalId,
    outcome: params.outcome,
    return_pct: params.returnPct ?? null,
    hold_duration_hours: params.holdDurationHours ?? null,
    logged_at: now,
    updated_at: now,
    resolution_source: src,
    resolved_at: params.outcome !== "pending" ? now : null,
    signal_label:
      signalLabel(params.module, snap) ||
      (typeof existing?.signal_label === "string" ? existing.signal_label : null),
    scoring_snapshot: snap,
  };

  let result = await supabase
    .from("signal_performance")
    .upsert(row, { onConflict: "user_id,module,signal_id" })
    .select(
      "id, module, signal_id, outcome, return_pct, hold_duration_hours, logged_at, resolution_source, signal_label",
    )
    .single();

  if (result.error?.message?.includes("column")) {
    const minimal = {
      user_id: userId,
      module: params.module,
      signal_id: signalId,
      outcome: params.outcome,
      return_pct: params.returnPct ?? null,
      logged_at: now,
      updated_at: now,
    };
    result = await supabase
      .from("signal_performance")
      .upsert(minimal, { onConflict: "user_id,module,signal_id" })
      .select(
        "id, module, signal_id, outcome, return_pct, hold_duration_hours, logged_at",
      )
      .single();
  }

  if (result.error || !result.data) {
    throw new Error(result.error?.message ?? "Could not save outcome");
  }
  return formatRow(result.data as Record<string, unknown>);
}

async function trackedKeys(
  supabase: ReturnType<typeof createClient>,
  userId: string,
): Promise<Set<string>> {
  const { data } = await supabase
    .from("signal_performance")
    .select("module, signal_id")
    .eq("user_id", userId)
    .limit(2000);

  const keys = new Set<string>();
  for (const row of data ?? []) {
    keys.add(`${row.module}:${normalizeSignalId(String(row.signal_id))}`);
  }
  return keys;
}

async function registerPending(
  supabase: ReturnType<typeof createClient>,
  userId: string,
  module: string,
  signalId: string,
  snapshot: Record<string, unknown>,
  source: string,
  tracked: Set<string>,
): Promise<boolean> {
  const sid = normalizeSignalId(signalId);
  if (!isUuid(sid)) return false;
  const key = `${module}:${sid}`;
  if (tracked.has(key)) return false;

  try {
    await logOutcomeDirect({
      module,
      signalId: sid,
      outcome: "pending",
      resolutionSource: source,
      signalSnapshot: snapshot,
    });
    tracked.add(key);
    return true;
  } catch {
    return false;
  }
}

export async function backfillTrackingDirect(): Promise<{
  registered: number;
  skipped: number;
  by_module: Record<string, { registered: number; skipped: number }>;
}> {
  const { supabase, userId, email } = await getSession();
  if (!userId) {
    return { registered: 0, skipped: 0, by_module: {} };
  }

  await ensureProfile(supabase, userId, email);
  const tracked = await trackedKeys(supabase, userId);
  const by_module: Record<string, { registered: number; skipped: number }> = {};
  let registered = 0;
  let skipped = 0;

  const signalTables: Array<{ module: string; table: string; order: string }> = [
    { module: "sports", table: "sports_signals", order: "event_start" },
    { module: "stock", table: "stock_signals", order: "data_as_of" },
    { module: "options", table: "options_signals", order: "expiration" },
    { module: "parlay", table: "parlays", order: "created_at" },
  ];

  for (const { module, table, order } of signalTables) {
    let modReg = 0;
    let modSkip = 0;
    const { data: rows } = await supabase
      .from(table)
      .select("*")
      .eq("user_id", userId)
      .order(order, { ascending: false })
      .limit(120);

    for (const row of rows ?? []) {
      const id = String((row as { id?: string }).id ?? "");
      if (!id) {
        modSkip += 1;
        continue;
      }
      const ok = await registerPending(
        supabase,
        userId,
        module,
        id,
        row as Record<string, unknown>,
        "auto_scan",
        tracked,
      );
      if (ok) modReg += 1;
      else modSkip += 1;
    }
    by_module[module] = { registered: modReg, skipped: modSkip };
    registered += modReg;
    skipped += modSkip;
  }

  const { data: watchlistItems } = await supabase
    .from("watchlist_items")
    .select("id, item_type, symbol, metadata")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(200);

  let wlReg = 0;
  let wlSkip = 0;
  for (const row of watchlistItems ?? []) {
    const item: WatchlistItem = {
      id: String(row.id),
      item_type: String(row.item_type),
      symbol: String(row.symbol),
      metadata: (row.metadata as Record<string, unknown>) ?? {},
    };
    const tracking = performanceTrackingForItem(item);
    if (!tracking || !isUuid(tracking.signalId)) {
      wlSkip += 1;
      continue;
    }
    const ok = await registerPending(
      supabase,
      userId,
      tracking.module,
      tracking.signalId,
      tracking.signalSnapshot ?? {},
      "watchlist",
      tracked,
    );
    if (ok) wlReg += 1;
    else wlSkip += 1;
  }
  by_module.watchlist = { registered: wlReg, skipped: wlSkip };
  registered += wlReg;
  skipped += wlSkip;

  return { registered, skipped, by_module };
}

export async function syncWatchlistDirect(): Promise<{
  synced: number;
  skipped: number;
  alreadyTracked: number;
  total: number;
  trackable: number;
  errors: string[];
}> {
  const { supabase, userId, email } = await getSession();
  if (!userId) {
    return {
      synced: 0,
      skipped: 0,
      alreadyTracked: 0,
      total: 0,
      trackable: 0,
      errors: ["Not signed in"],
    };
  }

  await ensureProfile(supabase, userId, email);

  const { data: watchlistItems, error: queryError } = await supabase
    .from("watchlist_items")
    .select("id, item_type, symbol, metadata, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(300);

  if (queryError) {
    return {
      synced: 0,
      skipped: 0,
      alreadyTracked: 0,
      total: 0,
      trackable: 0,
      errors: [queryError.message],
    };
  }

  const items = (watchlistItems ?? []).map((row) =>
    normalizeWatchlistItem({
      id: String(row.id),
      item_type: String(row.item_type),
      symbol: String(row.symbol),
      metadata: (row.metadata as Record<string, unknown>) ?? {},
      created_at: typeof row.created_at === "string" ? row.created_at : undefined,
    }),
  );

  let synced = 0;
  let skipped = 0;
  let alreadyTracked = 0;
  let trackable = 0;
  const errors: string[] = [];

  for (const item of items) {
    const tracking = performanceTrackingForItem(item);
    if (!tracking) {
      skipped += 1;
      continue;
    }
    if (!isUuid(tracking.signalId)) {
      skipped += 1;
      errors.push(`${effectiveItemType(item)}: invalid signal id`);
      continue;
    }
    trackable += 1;

    const existing = await getOutcomeDirect(tracking.module, tracking.signalId);
    if (existing) {
      // Re-stamp as user pick so watchlist saves show under Your picks.
      try {
        await logOutcomeDirect({
          module: tracking.module,
          signalId: tracking.signalId,
          outcome: existing.outcome === "pending" ? "pending" : existing.outcome,
          returnPct: existing.return_pct,
          resolutionSource: "watchlist",
          signalSnapshot: {
            ...(tracking.signalSnapshot ?? {}),
            pick_origin: "user",
            user_tracked: true,
          },
        });
      } catch {
        /* keep already-tracked count even if stamp fails */
      }
      alreadyTracked += 1;
      continue;
    }

    try {
      const saved = await logOutcomeDirect({
        module: tracking.module,
        signalId: tracking.signalId,
        outcome: "pending",
        resolutionSource: "watchlist",
        signalSnapshot: tracking.signalSnapshot,
      });
      if (saved) synced += 1;
      else {
        skipped += 1;
        errors.push(`${effectiveItemType(item)}: save returned empty`);
      }
    } catch (err) {
      skipped += 1;
      errors.push(
        `${effectiveItemType(item)}: ${err instanceof Error ? err.message : "save failed"}`,
      );
    }
  }

  return { synced, skipped, alreadyTracked, total: items.length, trackable, errors };
}

export async function updateOutcomeDirect(
  outcomeId: string,
  updates: {
    outcome?: string;
    returnPct?: number | null;
    holdDurationHours?: number | null;
  },
): Promise<PerformanceEntry | null> {
  const { supabase, userId } = await getSession();
  if (!userId) return null;

  const now = new Date().toISOString();
  const payload: Record<string, unknown> = { updated_at: now };
  if (updates.outcome) {
    payload.outcome = updates.outcome;
    payload.resolution_source = "manual_edit";
    payload.resolved_at = updates.outcome !== "pending" ? now : null;
  }
  if (updates.returnPct !== undefined) {
    payload.return_pct = updates.returnPct;
  }
  if (updates.holdDurationHours !== undefined) {
    payload.hold_duration_hours = updates.holdDurationHours;
  }

  const { data, error } = await supabase
    .from("signal_performance")
    .update(payload)
    .eq("id", outcomeId)
    .eq("user_id", userId)
    .select(
      "id, module, signal_id, outcome, return_pct, hold_duration_hours, logged_at, resolution_source, signal_label, scoring_snapshot",
    )
    .single();

  if (error || !data) return null;
  return formatRow(data as Record<string, unknown>);
}
