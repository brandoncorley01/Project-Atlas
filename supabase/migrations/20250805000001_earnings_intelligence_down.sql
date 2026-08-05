-- Rollback Earnings Intelligence tables
DROP TABLE IF EXISTS earnings_setup_outcomes;
DROP TABLE IF EXISTS earnings_setup_signals;
DELETE FROM mi_score_versions WHERE score_key = 'earnings_setup' AND version = 'earnings_setup_v1';
