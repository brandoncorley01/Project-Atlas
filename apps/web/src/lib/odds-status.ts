import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface OddsApiStatus {
  configured: boolean;
  connected: boolean;
  quota_exhausted?: boolean;
  total_remaining?: number | null;
  key_count?: number;
  keys?: Array<{
    index?: number;
    masked?: string;
    remaining?: number | null;
    exhausted?: boolean;
    valid?: boolean;
  }>;
  requests_remaining?: string | number | null;
  cache_has_data?: boolean;
  cache_has_events?: boolean;
  cache_within_ttl?: boolean;
  cache_rescore_free?: boolean;
  cache_age_minutes?: number | null;
  cache_fresh?: boolean;
  cache_needs_live_refresh?: boolean;
  near_term_leagues?: string[];
  league_catalog?: string[];
  near_term_event_count?: number;
  cache_ttl_minutes?: number;
  minutes_until_stale?: number;
  scan_scope?: string;
  max_sports_per_scan?: number;
  estimated_live_scan_credits?: number;
  monthly_capacity?: number;
  active_key_index?: number | null;
  error?: string | null;
}

export interface OpenAiStatus {
  configured?: boolean;
  connected?: boolean;
  model?: string | null;
  error?: string | null;
  features?: string[];
}

export function rescoreButtonLabel(
  status: Pick<
    OddsApiStatus,
    "cache_rescore_free" | "cache_fresh" | "cache_needs_live_refresh"
  > | null,
  loading = false,
): string {
  if (loading) return "Scanning…";
  if (!status?.cache_rescore_free) return "Scan sports odds";
  if (status.cache_fresh) return "Rescore cached (0 credits)";
  if (status.cache_needs_live_refresh) return "Rescore narrow cache (0 credits)";
  return "Rescore saved odds (0 credits)";
}

export async function fetchOddsProviderStatus(accessToken?: string, refresh = false): Promise<OddsApiStatus | null> {
  const data = await fetchProvidersStatus(accessToken, refresh);
  return data?.odds_api ?? null;
}

export async function fetchProvidersStatus(
  accessToken?: string,
  refresh = false,
): Promise<{
  finnhub?: Record<string, unknown>;
  odds_api?: OddsApiStatus;
  openai?: OpenAiStatus;
} | null> {
  const apiUrl = getApiUrl();
  const query = refresh ? "?refresh=true" : "";
  const res = await fetch(`${apiUrl}/providers/status${query}`, {
    headers: apiRequestHeaders(accessToken),
    cache: "no-store",
    credentials: usesBffProxy() ? "include" : "same-origin",
  });
  if (!res.ok) return null;
  return res.json();
}
