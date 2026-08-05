import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";
import {
  CLIENT_ALERTS,
  CLIENT_CONGRESS_TRADES,
  CLIENT_DARK_POOL,
  CLIENT_EARNINGS_DESK,
  CLIENT_EXIT_HEATMAP,
  CLIENT_FIXTURE_FRESHNESS,
  CLIENT_FLOW_CARDS,
  CLIENT_HEATMAP,
  CLIENT_PERFORMANCE,
  CLIENT_SECTOR_ROTATION,
  CLIENT_SMART_MONEY,
  CLIENT_WEATHER,
} from "@/lib/market-intelligence-fixtures";

/** Fail soft so UI never hangs forever on a cold/missing Render API. */
const MI_FETCH_TIMEOUT_MS = 8_000;
const MI_HEAVY_TIMEOUT_MS = 55_000;

async function getToken() {
  if (usesBffProxy()) return undefined;
  try {
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  } catch {
    return undefined;
  }
}

function init(token?: string, method = "GET", body?: unknown, timeoutMs = MI_FETCH_TIMEOUT_MS): RequestInit {
  return {
    method,
    headers: {
      ...apiRequestHeaders(token),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    credentials: usesBffProxy() ? "include" : "same-origin",
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutMs),
  };
}

export type Freshness = {
  provider_name?: string;
  data_timestamp?: string | null;
  evaluation_timestamp?: string;
  data_status?: string;
  data_freshness?: string;
  missing_fields?: string[];
};

export type MiSource = "api" | "client_fixture";

async function miFetch<T>(
  path: string,
  method = "GET",
  body?: unknown,
  timeoutMs = MI_FETCH_TIMEOUT_MS,
): Promise<T | null> {
  try {
    const token = await getToken();
    const res = await fetch(
      `${getApiUrl()}/market-intelligence${path}`,
      init(token, method, body, timeoutMs),
    );
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function withSource<T extends Record<string, unknown>>(payload: T, source: MiSource): T & { source: MiSource } {
  return { ...payload, source };
}

export async function fetchMiStatus() {
  const data = await miFetch<Record<string, unknown>>("/status");
  if (data) return withSource(data, "api");
  return withSource(
    {
      enabled: true,
      active_provider: {
        provider_id: "client_fixture",
        provider_name: "Atlas Client Fixture",
        default_data_status: "simulated",
        active: true,
      },
      note: "API market-intelligence routes unavailable — using client fixtures.",
    },
    "client_fixture",
  );
}

export async function fetchOptionsFlow(limit = 50) {
  const data = await miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    `/options/flow?limit=${limit}`,
    "GET",
    undefined,
    MI_HEAVY_TIMEOUT_MS,
  );
  // Treat HTTP 200 as API even when Yahoo returns an empty unusualness set.
  if (data && Array.isArray(data.items)) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_FLOW_CARDS.slice(0, limit),
      freshness: CLIENT_FIXTURE_FRESHNESS,
      disclaimer:
        "Showing simulated fixtures (API unreachable or still deploying). Data is not live.",
    },
    "client_fixture",
  );
}

export async function fetchLowPremium(filters?: Record<string, unknown>) {
  const data = await miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    "/options/low-premium",
    "POST",
    filters ?? {},
  );
  if (data?.items) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_FLOW_CARDS.filter((c) => Number(c.current_premium) <= 5).map((card) => ({
        event: {
          underlying: card.ticker,
          expiration: card.expiration,
          strike: card.strike,
          option_type: String(card.contract).includes("PUT") ? "put" : "call",
          contract_price: card.current_premium,
          midpoint: card.current_premium,
          estimated_premium: card.estimated_total_premium,
          contract_volume: card.volume,
          open_interest: card.open_interest,
          volume_oi_ratio: card.volume_oi_ratio,
          data_status: "simulated",
          idempotency_key: card.idempotency_key,
        },
        direction: card.direction,
        score: card.score,
        rank_score: card.unusual_score,
        spread_pct: card.bid_ask_spread_pct,
        review_zone: card.suggested_review_zone,
      })),
      freshness: CLIENT_FIXTURE_FRESHNESS,
      disclaimer: "Simulated low-premium list (API unavailable).",
    },
    "client_fixture",
  );
}

export async function fetchSmartMoney() {
  const data = await miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    "/options/smart-money",
  );
  if (data?.items) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_SMART_MONEY,
      freshness: CLIENT_FIXTURE_FRESHNESS,
      disclaimer: "Simulated concentrated-activity watchlist (API unavailable).",
    },
    "client_fixture",
  );
}

export async function fetchOptionsHeatmap() {
  const data = await miFetch<Record<string, unknown>>("/options/heatmap", "GET", undefined, MI_HEAVY_TIMEOUT_MS);
  if (data?.sectors) return withSource(data, "api");
  return withSource({ ...CLIENT_HEATMAP }, "client_fixture");
}

export async function fetchSignalHistory() {
  const data = await miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness }>("/options/signals/history");
  if (data?.items) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_FLOW_CARDS,
      freshness: CLIENT_FIXTURE_FRESHNESS,
    },
    "client_fixture",
  );
}

export async function fetchOptionsPerformance() {
  const data = await miFetch<Record<string, unknown>>("/options/performance");
  if (data) return withSource(data, "api");
  return withSource({ ...CLIENT_PERFORMANCE }, "client_fixture");
}

export async function fetchAlertSettings() {
  const data = await miFetch<{ items: Record<string, unknown>[]; allow_simulated_alerts?: boolean }>(
    "/options/alerts/settings",
  );
  if (data?.items) return withSource(data, "api");
  return withSource({ ...CLIENT_ALERTS }, "client_fixture");
}

export async function fetchMarketHeatmap() {
  const data = await miFetch<Record<string, unknown>>("/heatmap", "GET", undefined, MI_HEAVY_TIMEOUT_MS);
  if (data?.sectors) return withSource(data, "api");
  return withSource({ ...CLIENT_HEATMAP, color_by: "daily_return", heatmap_kind: "fixture" }, "client_fixture");
}

export async function fetchDarkPool(limit = 40) {
  const data = await miFetch<{
    items: Record<string, unknown>[];
    freshness?: Freshness;
    disclaimer?: string;
    week_start?: string;
    available?: boolean;
  }>(`/dark-pool?limit=${limit}`, "GET", undefined, MI_HEAVY_TIMEOUT_MS);
  if (data?.items) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_DARK_POOL,
      week_start: null,
      available: false,
      freshness: CLIENT_FIXTURE_FRESHNESS,
      disclaimer:
        "FINRA ATS dark-pool volume unavailable — API still deploying or unreachable. Not fabricated.",
    },
    "client_fixture",
  );
}

export async function fetchCongressTrades(limit = 40) {
  const data = await miFetch<{
    items: Record<string, unknown>[];
    freshness?: Freshness;
    disclaimer?: string;
    available?: boolean;
  }>(`/congress-trades?limit=${limit}`, "GET", undefined, MI_HEAVY_TIMEOUT_MS);
  if (data?.items) return withSource(data, "api");
  return withSource(
    {
      items: CLIENT_CONGRESS_TRADES,
      available: false,
      freshness: CLIENT_FIXTURE_FRESHNESS,
      disclaimer:
        "Congress TRADE disclosures unavailable — showing preview placeholders until API responds.",
    },
    "client_fixture",
  );
}

export async function fetchEarningsDesk() {
  const data = await miFetch<Record<string, unknown>>(
    "/earnings/desk",
    "GET",
    undefined,
    MI_HEAVY_TIMEOUT_MS,
  );
  if (data && (data.upcoming || data.recently_reviewed || data.micro_coattails)) {
    return withSource(data, "api");
  }
  return withSource({ ...CLIENT_EARNINGS_DESK }, "client_fixture");
}

export async function fetchSectorRotation() {
  const data = await miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness }>("/sector-rotation");
  if (data?.items) return withSource(data, "api");
  return withSource({ ...CLIENT_SECTOR_ROTATION }, "client_fixture");
}

export async function fetchSmartMoneyHeatmap() {
  const data = await miFetch<Record<string, unknown>>("/smart-money-heatmap");
  if (data?.sectors) return withSource(data, "api");
  return withSource({ ...CLIENT_HEATMAP }, "client_fixture");
}

export async function fetchMarketWeather() {
  const data = await miFetch<Record<string, unknown>>("/weather");
  if (data?.label) return withSource(data, "api");
  return withSource({ ...CLIENT_WEATHER }, "client_fixture");
}

export async function fetchHistoricalReplay() {
  const data = await miFetch<Record<string, unknown>>("/replay");
  if (data) return withSource(data, "api");
  return withSource(
    {
      available: false,
      outcome_engine_ready: true,
      message:
        "Historical replay needs persisted snapshots after the API migration is applied. Preview mode shows this placeholder.",
    },
    "client_fixture",
  );
}

export async function fetchPortfolioExitHeatmap(positions?: Record<string, unknown>[]) {
  const data = await miFetch<Record<string, unknown>>("/exit/portfolio-heatmap", "POST", {
    positions: positions ?? null,
  });
  if (data?.sectors || data?.tiles_detail) return withSource(data, "api");
  return withSource({ ...CLIENT_EXIT_HEATMAP }, "client_fixture");
}

export async function evaluateExit(position: Record<string, unknown>) {
  const data = await miFetch<Record<string, unknown>>("/exit/evaluate", "POST", position);
  if (data) return withSource(data, "api");
  return withSource(
    {
      symbol: position.symbol,
      exit_urgency: 58,
      action: "Tighten Stop",
      thesis_status: "intact",
      confidence: 64,
      explanation:
        "Tighten Stop. Preview fixture — connect Market Intelligence API for live evaluation.",
      data_status: "simulated",
    },
    "client_fixture",
  );
}
