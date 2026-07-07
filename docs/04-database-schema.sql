-- Project Atlas — Initial Database Schema
-- Run via Supabase SQL editor or: supabase db push

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE signal_module AS ENUM ('options', 'stock', 'sports', 'parlay');
CREATE TYPE signal_status AS ENUM ('active', 'expired', 'invalidated', 'closed');
CREATE TYPE news_sentiment AS ENUM ('bullish', 'bearish', 'neutral');
CREATE TYPE alert_type AS ENUM (
  'options_signal',
  'stock_signal',
  'sports_signal',
  'parlay_opportunity',
  'entry_reached',
  'profit_target',
  'stop_loss',
  'news_catalyst',
  'line_movement',
  'injury_update'
);
CREATE TYPE performance_outcome AS ENUM ('win', 'loss', 'scratch', 'pending');
CREATE TYPE parlay_style AS ENUM ('conservative', 'balanced', 'aggressive');

-- =============================================================================
-- PROFILES (extends Supabase auth.users)
-- =============================================================================

CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- WATCHLISTS
-- =============================================================================

CREATE TABLE watchlists (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'Default',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE watchlist_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  item_type TEXT NOT NULL CHECK (item_type IN ('ticker', 'sport_event', 'team')),
  symbol TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (watchlist_id, item_type, symbol)
);

-- =============================================================================
-- SHARED SIGNAL FIELDS (base pattern via JSONB + module tables)
-- =============================================================================

CREATE TABLE options_signals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  underlying TEXT NOT NULL,
  option_type TEXT NOT NULL CHECK (option_type IN ('call', 'put')),
  strike NUMERIC(12, 4) NOT NULL,
  expiration DATE NOT NULL,
  days_to_expiration INT NOT NULL,
  premium NUMERIC(12, 4),
  bid NUMERIC(12, 4),
  ask NUMERIC(12, 4),
  bid_ask_spread_pct NUMERIC(8, 4),
  volume INT,
  open_interest INT,
  delta NUMERIC(8, 6),
  gamma NUMERIC(8, 6),
  theta NUMERIC(8, 6),
  implied_volatility NUMERIC(8, 4),
  entry_zone JSONB,
  profit_targets JSONB,
  max_loss NUMERIC(12, 4),
  expected_hold_time TEXT,
  confidence_score NUMERIC(5, 2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
  risk_score NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  opportunity_score NUMERIC(5, 2) NOT NULL CHECK (opportunity_score BETWEEN 0 AND 100),
  recommendation TEXT NOT NULL,
  explanation TEXT NOT NULL,
  bull_case TEXT,
  bear_case TEXT,
  invalidation TEXT,
  suggested_action TEXT,
  risk_warning TEXT NOT NULL,
  scoring_snapshot JSONB DEFAULT '{}',
  status signal_status NOT NULL DEFAULT 'active',
  data_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE stock_signals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  current_price NUMERIC(12, 4),
  entry_range JSONB,
  stop_loss NUMERIC(12, 4),
  profit_targets JSONB,
  expected_hold_time TEXT,
  timeframe TEXT,
  technicals JSONB DEFAULT '{}',
  confidence_score NUMERIC(5, 2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
  risk_score NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  opportunity_score NUMERIC(5, 2) NOT NULL CHECK (opportunity_score BETWEEN 0 AND 100),
  recommendation TEXT NOT NULL,
  explanation TEXT NOT NULL,
  bull_case TEXT,
  bear_case TEXT,
  invalidation TEXT,
  suggested_action TEXT,
  risk_warning TEXT NOT NULL,
  scoring_snapshot JSONB DEFAULT '{}',
  status signal_status NOT NULL DEFAULT 'active',
  data_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sports_signals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  sport TEXT NOT NULL,
  event_name TEXT NOT NULL,
  event_start TIMESTAMPTZ,
  bet_type TEXT NOT NULL,
  selection TEXT NOT NULL,
  odds_american INT,
  odds_decimal NUMERIC(8, 4),
  expected_value NUMERIC(8, 4),
  line_movement JSONB,
  injury_impact TEXT,
  weather_impact TEXT,
  travel_rest_impact TEXT,
  public_betting_pct NUMERIC(5, 2),
  sharp_indicator TEXT,
  confidence_score NUMERIC(5, 2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
  risk_score NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  opportunity_score NUMERIC(5, 2) NOT NULL CHECK (opportunity_score BETWEEN 0 AND 100),
  recommendation TEXT NOT NULL,
  explanation TEXT NOT NULL,
  bull_case TEXT,
  bear_case TEXT,
  invalidation TEXT,
  suggested_action TEXT,
  risk_warning TEXT NOT NULL,
  scoring_snapshot JSONB DEFAULT '{}',
  status signal_status NOT NULL DEFAULT 'active',
  data_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE parlays (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT,
  style parlay_style NOT NULL DEFAULT 'balanced',
  combined_odds_american INT,
  combined_odds_decimal NUMERIC(10, 4),
  expected_value NUMERIC(8, 4),
  correlation_warning TEXT,
  confidence_score NUMERIC(5, 2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
  risk_score NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  opportunity_score NUMERIC(5, 2) NOT NULL CHECK (opportunity_score BETWEEN 0 AND 100),
  recommendation TEXT NOT NULL,
  explanation TEXT NOT NULL,
  risk_warning TEXT NOT NULL,
  status signal_status NOT NULL DEFAULT 'active',
  data_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE parlay_legs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  parlay_id UUID NOT NULL REFERENCES parlays(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  leg_order INT NOT NULL,
  sport TEXT NOT NULL,
  event_name TEXT NOT NULL,
  bet_type TEXT NOT NULL,
  selection TEXT NOT NULL,
  odds_american INT,
  leg_reason TEXT,
  sports_signal_id UUID REFERENCES sports_signals(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- NEWS
-- =============================================================================

CREATE TABLE news_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  summary TEXT,
  published_at TIMESTAMPTZ,
  sentiment news_sentiment NOT NULL DEFAULT 'neutral',
  impact_score NUMERIC(5, 2) NOT NULL CHECK (impact_score BETWEEN 0 AND 100),
  time_sensitivity_score NUMERIC(5, 2) CHECK (time_sensitivity_score BETWEEN 0 AND 100),
  explanation TEXT,
  related_tickers TEXT[] DEFAULT '{}',
  related_sports TEXT[] DEFAULT '{}',
  raw_payload JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- ALERTS
-- =============================================================================

CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  alert_type alert_type NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  module signal_module,
  reference_id UUID,
  read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- PERFORMANCE & NOTES
-- =============================================================================

CREATE TABLE signal_performance (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  module signal_module NOT NULL,
  signal_id UUID NOT NULL,
  outcome performance_outcome NOT NULL DEFAULT 'pending',
  return_pct NUMERIC(10, 4),
  hold_duration_hours NUMERIC(10, 2),
  logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, module, signal_id)
);

CREATE TABLE user_notes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  module signal_module,
  signal_id UUID,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE performance_summaries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  module signal_module,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  total_signals INT DEFAULT 0,
  wins INT DEFAULT 0,
  losses INT DEFAULT 0,
  scratches INT DEFAULT 0,
  avg_return_pct NUMERIC(10, 4),
  avg_loss_pct NUMERIC(10, 4),
  avg_hold_hours NUMERIC(10, 2),
  confidence_accuracy JSONB DEFAULT '{}',
  strategy_breakdown JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX idx_options_signals_user_score ON options_signals (user_id, opportunity_score DESC);
CREATE INDEX idx_options_signals_user_created ON options_signals (user_id, created_at DESC);
CREATE INDEX idx_stock_signals_user_score ON stock_signals (user_id, opportunity_score DESC);
CREATE INDEX idx_sports_signals_user_score ON sports_signals (user_id, opportunity_score DESC);
CREATE INDEX idx_parlays_user_score ON parlays (user_id, opportunity_score DESC);
CREATE INDEX idx_news_items_user_published ON news_items (user_id, published_at DESC);
CREATE INDEX idx_news_items_tickers ON news_items USING GIN (related_tickers);
CREATE INDEX idx_alerts_user_unread ON alerts (user_id, read, created_at DESC);
CREATE INDEX idx_watchlist_items_user ON watchlist_items (user_id);

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE options_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE sports_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE parlays ENABLE ROW LEVEL SECURITY;
ALTER TABLE parlay_legs ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_summaries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_select_own" ON profiles FOR SELECT USING (id = auth.uid());
CREATE POLICY "profiles_update_own" ON profiles FOR UPDATE USING (id = auth.uid());

CREATE POLICY "watchlists_own" ON watchlists FOR ALL USING (user_id = auth.uid());
CREATE POLICY "watchlist_items_own" ON watchlist_items FOR ALL USING (user_id = auth.uid());
CREATE POLICY "options_signals_own" ON options_signals FOR ALL USING (user_id = auth.uid());
CREATE POLICY "stock_signals_own" ON stock_signals FOR ALL USING (user_id = auth.uid());
CREATE POLICY "sports_signals_own" ON sports_signals FOR ALL USING (user_id = auth.uid());
CREATE POLICY "parlays_own" ON parlays FOR ALL USING (user_id = auth.uid());
CREATE POLICY "parlay_legs_own" ON parlay_legs FOR ALL USING (user_id = auth.uid());
CREATE POLICY "news_items_own" ON news_items FOR ALL USING (user_id = auth.uid());
CREATE POLICY "alerts_own" ON alerts FOR ALL USING (user_id = auth.uid());
CREATE POLICY "signal_performance_own" ON signal_performance FOR ALL USING (user_id = auth.uid());
CREATE POLICY "user_notes_own" ON user_notes FOR ALL USING (user_id = auth.uid());
CREATE POLICY "performance_summaries_own" ON performance_summaries FOR ALL USING (user_id = auth.uid());

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, email)
  VALUES (NEW.id, NEW.email);
  INSERT INTO watchlists (user_id, name)
  VALUES (NEW.id, 'Default');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
