-- Market & Options Intelligence (additive — does not modify existing tables)
-- Rollback: see 20250724000001_market_options_intelligence_down.sql

CREATE TABLE IF NOT EXISTS mi_provider_status (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  provider_key TEXT NOT NULL,
  provider_name TEXT NOT NULL,
  data_status TEXT NOT NULL DEFAULT 'simulated',
  last_success_at TIMESTAMPTZ,
  last_error TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, provider_key)
);

CREATE TABLE IF NOT EXISTS mi_score_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_key TEXT NOT NULL,
  version TEXT NOT NULL,
  formula_summary TEXT NOT NULL,
  weights JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (score_key, version)
);

CREATE TABLE IF NOT EXISTS options_activity_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  underlying TEXT NOT NULL,
  option_type TEXT NOT NULL CHECK (option_type IN ('call', 'put')),
  strike NUMERIC(18, 6) NOT NULL,
  expiration DATE NOT NULL,
  trade_timestamp TIMESTAMPTZ NOT NULL,
  contract_price NUMERIC(18, 6),
  bid NUMERIC(18, 6),
  ask NUMERIC(18, 6),
  midpoint NUMERIC(18, 6),
  contracts INTEGER,
  estimated_premium NUMERIC(20, 4),
  contract_volume INTEGER,
  open_interest INTEGER,
  volume_oi_ratio NUMERIC(18, 6),
  implied_volatility NUMERIC(18, 8),
  delta NUMERIC(18, 8),
  execution_class TEXT,
  flow_class TEXT,
  open_close TEXT,
  data_source TEXT NOT NULL,
  source_event_id TEXT,
  idempotency_key TEXT NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  data_status TEXT NOT NULL DEFAULT 'simulated',
  data_timestamp TIMESTAMPTZ,
  raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_options_activity_underlying
  ON options_activity_events (user_id, underlying, trade_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_options_activity_source
  ON options_activity_events (user_id, data_source, source_event_id);

CREATE TABLE IF NOT EXISTS options_activity_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  event_id UUID NOT NULL REFERENCES options_activity_events(id) ON DELETE CASCADE,
  score_version TEXT NOT NULL,
  overall_score NUMERIC(6, 2) NOT NULL,
  confidence NUMERIC(6, 2) NOT NULL,
  data_quality TEXT NOT NULL,
  direction TEXT NOT NULL,
  component_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
  positive_contributors JSONB NOT NULL DEFAULT '[]'::jsonb,
  negative_contributors JSONB NOT NULL DEFAULT '[]'::jsonb,
  missing_penalties JSONB NOT NULL DEFAULT '[]'::jsonb,
  weights JSONB NOT NULL DEFAULT '{}'::jsonb,
  evaluation_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  data_timestamp TIMESTAMPTZ,
  data_freshness TEXT,
  UNIQUE (event_id, score_version)
);

CREATE TABLE IF NOT EXISTS options_intel_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  event_id UUID REFERENCES options_activity_events(id) ON DELETE SET NULL,
  underlying TEXT NOT NULL,
  option_type TEXT NOT NULL,
  strike NUMERIC(18, 6) NOT NULL,
  expiration DATE NOT NULL,
  direction TEXT NOT NULL,
  unusual_score NUMERIC(6, 2) NOT NULL,
  confidence NUMERIC(6, 2) NOT NULL,
  risk_level TEXT NOT NULL,
  liquidity_grade TEXT NOT NULL,
  premium_at_signal NUMERIC(18, 6),
  underlying_price_at_signal NUMERIC(18, 6),
  score_version TEXT NOT NULL,
  explanation TEXT,
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_status TEXT NOT NULL DEFAULT 'simulated',
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'active',
  UNIQUE (user_id, underlying, option_type, strike, expiration, detected_at)
);

CREATE INDEX IF NOT EXISTS idx_options_intel_signals_user_detected
  ON options_intel_signals (user_id, detected_at DESC);

CREATE TABLE IF NOT EXISTS options_intel_signal_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  signal_id UUID NOT NULL REFERENCES options_intel_signals(id) ON DELETE CASCADE,
  underlying_high NUMERIC(18, 6),
  underlying_low NUMERIC(18, 6),
  contract_high NUMERIC(18, 6),
  contract_low NUMERIC(18, 6),
  mfe_pct NUMERIC(12, 4),
  mae_pct NUMERIC(12, 4),
  time_to_mfe_hours NUMERIC(12, 2),
  hit_25 BOOLEAN,
  hit_50 BOOLEAN,
  hit_100 BOOLEAN,
  hit_200 BOOLEAN,
  hit_stop BOOLEAN,
  expired_worthless BOOLEAN,
  iv_compression BOOLEAN,
  interval_returns JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_completeness TEXT NOT NULL DEFAULT 'partial',
  evaluation_status TEXT NOT NULL DEFAULT 'pending',
  evaluated_at TIMESTAMPTZ,
  UNIQUE (signal_id)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  snapshot_key TEXT NOT NULL,
  as_of TIMESTAMPTZ NOT NULL,
  data_status TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, snapshot_key, as_of)
);

CREATE TABLE IF NOT EXISTS sector_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  sector TEXT NOT NULL,
  as_of TIMESTAMPTZ NOT NULL,
  classification TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sector_snapshots_user_asof
  ON sector_snapshots (user_id, as_of DESC);

CREATE TABLE IF NOT EXISTS market_weather_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  as_of TIMESTAMPTZ NOT NULL,
  label TEXT NOT NULL,
  confidence NUMERIC(6, 2) NOT NULL,
  risk_level TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_status TEXT NOT NULL,
  score_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS position_evaluations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  position_key TEXT NOT NULL,
  module TEXT NOT NULL,
  symbol TEXT NOT NULL,
  as_of TIMESTAMPTZ NOT NULL,
  exit_urgency NUMERIC(6, 2) NOT NULL,
  action_class TEXT NOT NULL,
  thesis_status TEXT NOT NULL,
  confidence NUMERIC(6, 2) NOT NULL,
  explanation TEXT NOT NULL,
  components JSONB NOT NULL DEFAULT '{}'::jsonb,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  score_version TEXT NOT NULL,
  data_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_position_evaluations_user_asof
  ON position_evaluations (user_id, as_of DESC);

CREATE TABLE IF NOT EXISTS mi_alert_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  alert_type TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  threshold NUMERIC(12, 4),
  cooldown_minutes INTEGER NOT NULL DEFAULT 60,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, alert_type)
);

CREATE TABLE IF NOT EXISTS mi_alert_dedup (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  dedup_key TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  last_sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, dedup_key)
);

-- Seed active score versions (global reference rows; user_id not required)
INSERT INTO mi_score_versions (score_key, version, formula_summary, weights, active)
VALUES
  (
    'options_activity',
    'options_activity_v1',
    'Volume/OI, premium size, spread quality, flow class, delta/moneyness, confirmation penalties',
    '{"volume_oi":0.22,"premium":0.18,"spread":0.12,"flow_class":0.12,"repeat":0.1,"delta":0.08,"momentum":0.08,"news":0.05,"regime":0.05}'::jsonb,
    true
  ),
  (
    'exit_urgency',
    'exit_v1',
    'Momentum, trend, volume, options flow, sector/market regime, thesis, R:R, event risk',
    '{"momentum":0.18,"trend":0.16,"volume":0.1,"options":0.12,"sector":0.1,"market":0.1,"thesis":0.12,"reward_risk":0.07,"event":0.05}'::jsonb,
    true
  ),
  (
    'market_weather',
    'weather_v1',
    'Index momentum, breadth proxy, sector leadership, options bias, volatility regime',
    '{"index":0.25,"breadth":0.2,"sectors":0.2,"options":0.15,"volatility":0.1,"news":0.1}'::jsonb,
    true
  )
ON CONFLICT (score_key, version) DO NOTHING;
