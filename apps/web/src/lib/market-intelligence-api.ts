import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

function init(token?: string, method = "GET", body?: unknown): RequestInit {
  return {
    method,
    headers: {
      ...apiRequestHeaders(token),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    credentials: usesBffProxy() ? "include" : "same-origin",
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
  };
}

async function miFetch<T>(path: string, method = "GET", body?: unknown): Promise<T | null> {
  const token = await getToken();
  try {
    const res = await fetch(`${getApiUrl()}/market-intelligence${path}`, init(token, method, body));
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export type Freshness = {
  provider_name?: string;
  data_timestamp?: string | null;
  evaluation_timestamp?: string;
  data_status?: string;
  data_freshness?: string;
  missing_fields?: string[];
};

export async function fetchMiStatus() {
  return miFetch<Record<string, unknown>>("/status");
}

export async function fetchOptionsFlow(limit = 50) {
  return miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    `/options/flow?limit=${limit}`,
  );
}

export async function fetchLowPremium(filters?: Record<string, unknown>) {
  return miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    "/options/low-premium",
    "POST",
    filters ?? {},
  );
}

export async function fetchSmartMoney() {
  return miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness; disclaimer?: string }>(
    "/options/smart-money",
  );
}

export async function fetchOptionsHeatmap() {
  return miFetch<Record<string, unknown>>("/options/heatmap");
}

export async function fetchSignalHistory() {
  return miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness }>("/options/signals/history");
}

export async function fetchOptionsPerformance() {
  return miFetch<Record<string, unknown>>("/options/performance");
}

export async function fetchAlertSettings() {
  return miFetch<{ items: Record<string, unknown>[]; allow_simulated_alerts?: boolean }>(
    "/options/alerts/settings",
  );
}

export async function fetchMarketHeatmap() {
  return miFetch<Record<string, unknown>>("/heatmap");
}

export async function fetchSectorRotation() {
  return miFetch<{ items: Record<string, unknown>[]; freshness?: Freshness }>("/sector-rotation");
}

export async function fetchSmartMoneyHeatmap() {
  return miFetch<Record<string, unknown>>("/smart-money-heatmap");
}

export async function fetchMarketWeather() {
  return miFetch<Record<string, unknown>>("/weather");
}

export async function fetchHistoricalReplay() {
  return miFetch<Record<string, unknown>>("/replay");
}

export async function fetchPortfolioExitHeatmap(positions?: Record<string, unknown>[]) {
  return miFetch<Record<string, unknown>>("/exit/portfolio-heatmap", "POST", {
    positions: positions ?? null,
  });
}

export async function evaluateExit(position: Record<string, unknown>) {
  return miFetch<Record<string, unknown>>("/exit/evaluate", "POST", position);
}
