-- Rollback for 20250710000001_sports_intelligence.sql
-- Run manually if you need to remove the intelligence layer tables.

DROP POLICY IF EXISTS event_intel_consensus_own ON event_intelligence_consensus;
DROP POLICY IF EXISTS sports_expert_perf_own ON sports_expert_performance;
DROP POLICY IF EXISTS sports_expert_preds_own ON sports_expert_predictions;
DROP POLICY IF EXISTS sports_intel_items_own ON sports_intelligence_items;
DROP POLICY IF EXISTS sports_experts_own ON sports_experts;
DROP POLICY IF EXISTS sports_intel_sources_own ON sports_intelligence_sources;

DROP TABLE IF EXISTS event_intelligence_consensus;
DROP TABLE IF EXISTS sports_expert_performance;
DROP TABLE IF EXISTS sports_expert_predictions;
DROP TABLE IF EXISTS sports_intelligence_items;
DROP TABLE IF EXISTS sports_experts;
DROP TABLE IF EXISTS sports_intelligence_sources;
