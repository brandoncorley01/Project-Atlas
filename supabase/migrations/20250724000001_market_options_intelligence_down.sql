-- Rollback Market & Options Intelligence tables

DROP TABLE IF EXISTS mi_alert_dedup;
DROP TABLE IF EXISTS mi_alert_settings;
DROP TABLE IF EXISTS position_evaluations;
DROP TABLE IF EXISTS market_weather_snapshots;
DROP TABLE IF EXISTS sector_snapshots;
DROP TABLE IF EXISTS market_snapshots;
DROP TABLE IF EXISTS options_intel_signal_outcomes;
DROP TABLE IF EXISTS options_intel_signals;
DROP TABLE IF EXISTS options_activity_scores;
DROP TABLE IF EXISTS options_activity_events;
DROP TABLE IF EXISTS mi_score_versions;
DROP TABLE IF EXISTS mi_provider_status;
