-- Earnings Intelligence (additive under Market Intelligence)
-- Paper-only setups + learning outcomes. Does not enable live trading.

CREATE TABLE IF NOT EXISTS earnings_setup_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  direction TEXT,
  phase TEXT,
  strategy TEXT,
  confidence NUMERIC(6, 2),
  expected_move_pct NUMERIC(10, 4),
  expected_value NUMERIC(14, 4),
  paper_position_size_usd NUMERIC(14, 4),
  paper_only BOOLEAN NOT NULL DEFAULT true,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_status TEXT NOT NULL DEFAULT 'simulated',
  score_version TEXT NOT NULL DEFAULT 'earnings_setup_v1',
  evaluated_day DATE NOT NULL DEFAULT (CURRENT_DATE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, symbol, evaluated_day)
);

CREATE INDEX IF NOT EXISTS idx_earnings_setup_signals_user
  ON earnings_setup_signals (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS earnings_setup_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  symbol TEXT,
  recommendation_type TEXT,
  strategy TEXT,
  predicted_direction TEXT,
  predicted_move_pct NUMERIC(10, 4),
  predicted_iv_crush_pct NUMERIC(10, 4),
  actual_direction TEXT,
  actual_move_pct NUMERIC(10, 4),
  actual_iv_crush_pct NUMERIC(10, 4),
  paper_entry NUMERIC(18, 6),
  paper_exit NUMERIC(18, 6),
  mfe_pct NUMERIC(10, 4),
  mae_pct NUMERIC(10, 4),
  net_result_after_costs NUMERIC(14, 4),
  confidence_at_signal NUMERIC(6, 2),
  micro_coattail BOOLEAN NOT NULL DEFAULT false,
  paper_only BOOLEAN NOT NULL DEFAULT true,
  policy_auto_update BOOLEAN NOT NULL DEFAULT false,
  live_trading_enabled BOOLEAN NOT NULL DEFAULT false,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_earnings_setup_outcomes_user
  ON earnings_setup_outcomes (user_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_earnings_setup_outcomes_micro
  ON earnings_setup_outcomes (user_id, micro_coattail, recorded_at DESC);

INSERT INTO mi_score_versions (score_key, version, formula_summary, weights, active)
VALUES (
  'earnings_setup',
  'earnings_setup_v1',
  'Expected move, historical move, liquidity, breakeven reach, EV after costs, sentiment/sector, IV crush',
  '{"expected_move":0.22,"historical_move":0.14,"liquidity":0.16,"breakeven_reach":0.16,"expected_value":0.18,"sentiment_sector":0.08,"iv_crush_risk":0.06}'::jsonb,
  true
)
ON CONFLICT (score_key, version) DO NOTHING;
