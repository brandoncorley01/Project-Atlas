-- Sports Intelligence Layer (additive — does not modify existing tables)
-- Rollback: drop tables in reverse order

CREATE TABLE IF NOT EXISTS sports_intelligence_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  provider_key TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  base_url TEXT,
  enabled BOOLEAN NOT NULL DEFAULT true,
  reliability_score NUMERIC(5,2) DEFAULT 0.5,
  configuration JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, provider_key)
);

CREATE TABLE IF NOT EXISTS sports_experts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_id UUID REFERENCES sports_intelligence_sources(id) ON DELETE SET NULL,
  display_name TEXT NOT NULL,
  external_identifier TEXT,
  specialty_sports TEXT[] DEFAULT '{}',
  specialty_markets TEXT[] DEFAULT '{}',
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sports_intelligence_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  signal_id UUID REFERENCES sports_signals(id) ON DELETE CASCADE,
  event_id TEXT,
  source_id UUID REFERENCES sports_intelligence_sources(id) ON DELETE SET NULL,
  external_id TEXT,
  source_type TEXT NOT NULL,
  author_name TEXT,
  analyst_id UUID REFERENCES sports_experts(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  source_url TEXT,
  published_at TIMESTAMPTZ,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  predicted_market TEXT,
  predicted_selection TEXT,
  predicted_line NUMERIC,
  predicted_odds INTEGER,
  confidence_score NUMERIC(5,2),
  sentiment TEXT,
  key_arguments JSONB DEFAULT '[]'::jsonb,
  risk_factors JSONB DEFAULT '[]'::jsonb,
  injury_mentions JSONB DEFAULT '[]'::jsonb,
  relevance_score NUMERIC(5,2) DEFAULT 0,
  freshness_score NUMERIC(5,2) DEFAULT 0,
  content_hash TEXT,
  duplicate_group_id TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  raw_metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sports_intel_items_signal
  ON sports_intelligence_items(user_id, signal_id, status);
CREATE INDEX IF NOT EXISTS idx_sports_intel_items_hash
  ON sports_intelligence_items(user_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_sports_intel_items_event
  ON sports_intelligence_items(user_id, event_id);

CREATE TABLE IF NOT EXISTS sports_expert_predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  expert_id UUID REFERENCES sports_experts(id) ON DELETE SET NULL,
  signal_id UUID REFERENCES sports_signals(id) ON DELETE CASCADE,
  event_id TEXT,
  intelligence_item_id UUID REFERENCES sports_intelligence_items(id) ON DELETE SET NULL,
  market_type TEXT,
  selection TEXT,
  line NUMERIC,
  odds INTEGER,
  confidence_score NUMERIC(5,2),
  supporting_reasons JSONB DEFAULT '[]'::jsonb,
  opposing_reasons JSONB DEFAULT '[]'::jsonb,
  published_at TIMESTAMPTZ,
  result TEXT,
  profit_units NUMERIC,
  closing_line NUMERIC,
  closing_line_value NUMERIC,
  graded_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sports_expert_performance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  expert_id UUID NOT NULL REFERENCES sports_experts(id) ON DELETE CASCADE,
  league TEXT,
  market_type TEXT,
  sample_size INTEGER DEFAULT 0,
  wins INTEGER DEFAULT 0,
  losses INTEGER DEFAULT 0,
  pushes INTEGER DEFAULT 0,
  win_rate NUMERIC(5,2),
  roi NUMERIC(8,2),
  profit_units NUMERIC(10,2),
  average_clv NUMERIC(8,2),
  last_30_day_roi NUMERIC(8,2),
  reliability_score NUMERIC(5,2) DEFAULT 0.5,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, expert_id, league, market_type)
);

CREATE TABLE IF NOT EXISTS event_intelligence_consensus (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  signal_id UUID NOT NULL REFERENCES sports_signals(id) ON DELETE CASCADE,
  event_id TEXT,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expert_count INTEGER DEFAULT 0,
  source_count INTEGER DEFAULT 0,
  home_support_pct NUMERIC(5,2),
  away_support_pct NUMERIC(5,2),
  over_support_pct NUMERIC(5,2),
  under_support_pct NUMERIC(5,2),
  top_consensus_pick TEXT,
  weighted_consensus_score NUMERIC(5,2),
  contrarian_summary TEXT,
  majority_reasoning JSONB DEFAULT '[]'::jsonb,
  minority_reasoning JSONB DEFAULT '[]'::jsonb,
  key_news_summary TEXT,
  injury_impact_summary TEXT,
  confidence_adjustment NUMERIC(5,2) DEFAULT 0,
  model_agreement_status TEXT,
  adjustment_payload JSONB DEFAULT '{}'::jsonb,
  verdict TEXT,
  confidence_label TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, signal_id)
);

ALTER TABLE sports_intelligence_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sports_experts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sports_intelligence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE sports_expert_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sports_expert_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_intelligence_consensus ENABLE ROW LEVEL SECURITY;

CREATE POLICY sports_intel_sources_own ON sports_intelligence_sources
  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY sports_experts_own ON sports_experts
  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY sports_intel_items_own ON sports_intelligence_items
  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY sports_expert_preds_own ON sports_expert_predictions
  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY sports_expert_perf_own ON sports_expert_performance
  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY event_intel_consensus_own ON event_intelligence_consensus
  FOR ALL USING (auth.uid() = user_id);
