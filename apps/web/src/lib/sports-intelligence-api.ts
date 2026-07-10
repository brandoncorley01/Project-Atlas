import { apiFetch } from "@/lib/api";
import { getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface AtlasIntelligencePayload {
  enabled: boolean;
  signal_id?: string;
  status?: string;
  message?: string;
  last_updated?: string | null;
  source_transparency?: {
    sources_analyzed: number;
    unique_analysts: number;
    items_active: number;
    video_transcripts_available: boolean;
    injury_confirmed: boolean;
    atlas_summarized: boolean;
  };
  atlas_recommendation?: {
    selection?: string;
    odds_american?: number;
    raw_confidence: number;
    adjusted_confidence: number;
    confidence_label: string;
    expected_value?: number;
    risk_score?: number;
    primary_reasons?: string[];
    invalidation?: string | null;
  };
  expert_consensus?: {
    expert_count: number;
    source_count: number;
    weighted_consensus_score: number;
    majority_selection?: string | null;
    minority_selection?: string | null;
    home_support_pct?: number | null;
    away_support_pct?: number | null;
    experts_agreeing_with_atlas: number;
    experts_disagreeing_with_atlas: number;
    model_agreement: string;
  };
  analyst_cards?: Array<{
    source: string;
    analyst?: string | null;
    pick?: string | null;
    market?: string | null;
    reasoning?: string[];
    confidence?: number | null;
    published_at?: string | null;
    url?: string | null;
    source_type?: string;
  }>;
  news_updates?: Array<{
    title?: string;
    summary?: string;
    url?: string | null;
    published_at?: string | null;
    type?: string;
  }>;
  bull_case?: string | null;
  bear_case?: string | null;
  verdict?: string;
  adjustment?: {
    expert: number;
    news: number;
    injury: number;
    disagreement_penalty: number;
    total: number;
    explanation: string[];
  };
  disclaimer?: string;
}

export async function fetchIntelligenceStatus(): Promise<{ enabled: boolean }> {
  try {
    const url = `${getApiUrl()}/signals/sports/intelligence/status`;
    const response = await fetch(url, {
      cache: "no-store",
      credentials: usesBffProxy() ? "include" : "same-origin",
    });
    if (!response.ok) return { enabled: false };
    return (await response.json()) as { enabled: boolean };
  } catch {
    return { enabled: false };
  }
}

export async function fetchSportsIntelligence(
  signalId: string,
  token: string,
): Promise<AtlasIntelligencePayload | null> {
  try {
    return await apiFetch<AtlasIntelligencePayload>(
      `/signals/sports/${signalId}/intelligence`,
      token,
    );
  } catch (err) {
    if (err instanceof Error && /404|disabled/i.test(err.message)) {
      return null;
    }
    throw err;
  }
}

export async function refreshSportsIntelligence(
  signalId: string,
  token: string,
): Promise<AtlasIntelligencePayload> {
  return apiFetch<AtlasIntelligencePayload>(
    `/signals/sports/${signalId}/intelligence/refresh`,
    token,
    { method: "POST" },
  );
}
