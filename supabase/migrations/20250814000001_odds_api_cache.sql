-- Durable Odds API slate cache (shared, not per-user).
-- Survives Render ephemeral disk wipes so Scan/Rescore stay free after Fetch.
-- Written/read only by the API service role — no anon/authenticated policies.

CREATE TABLE IF NOT EXISTS odds_api_cache (
  cache_key TEXT PRIMARY KEY DEFAULT 'default',
  fetched_at TIMESTAMPTZ NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0,
  near_term_event_count INTEGER NOT NULL DEFAULT 0,
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  events JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_odds_api_cache_fetched_at
  ON odds_api_cache (fetched_at DESC);

ALTER TABLE odds_api_cache ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE odds_api_cache IS
  'Shared The Odds API event slate. Service-role only. Disk .odds_cache.json is a hot mirror.';
