-- Enrich outcome logging for calibration and auto-resolution tracking.

ALTER TABLE signal_performance
  ADD COLUMN IF NOT EXISTS opportunity_score NUMERIC(6, 2),
  ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(6, 2),
  ADD COLUMN IF NOT EXISTS scoring_snapshot JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS resolution_source TEXT,
  ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS signal_label TEXT;

CREATE INDEX IF NOT EXISTS idx_signal_performance_user_logged
  ON signal_performance (user_id, logged_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_performance_user_module
  ON signal_performance (user_id, module, outcome);
