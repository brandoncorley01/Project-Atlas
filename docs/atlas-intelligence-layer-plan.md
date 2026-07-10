# Atlas Sports Intelligence Layer — Implementation Plan

## Objective

Add a modular **Sports Intelligence and Expert Consensus Layer** that enriches Atlas sports picks with news, analyst context, consensus, and bounded confidence adjustments — without replacing the existing prediction engine or UI.

## Existing Assets Reused

| Area | Files |
|------|--------|
| Sports scan | `apps/api/app/services/sports_service.py` |
| News RSS | `apps/api/app/providers/sports/sports_news.py` |
| Insight / explain | `apps/api/app/services/sports_insight_service.py` |
| LLM | `apps/api/app/services/llm_service.py` |
| Signal API | `apps/api/app/routers/signals.py`, `signal_service.py` |
| Jobs | `apps/api/app/jobs/nightly_learning.py`, `refresh_sports.py` |
| Sports UI | `SportsSignalsView.tsx`, `SportsSignalCard.tsx`, `/sports/[id]` |
| Explain UI | `AtlasExplainButton.tsx` |

## New Files Added

```
apps/api/app/sports_intelligence/
  types.py
  providers/base.py
  providers/rss_provider.py
  providers/mock_provider.py
  providers/registry.py
  normalization.py
  dedup.py
  consensus.py
  adjustment.py
  extraction.py
  service.py

apps/api/app/services/sports_intelligence_db.py
apps/api/app/jobs/refresh_sports_intelligence.py
apps/api/app/routers/sports_intelligence.py

supabase/migrations/20250710000001_sports_intelligence.sql

apps/web/src/components/sports/AtlasIntelligencePanel.tsx
apps/web/src/lib/sports-intelligence-api.ts

docs/sports-intelligence-overview.md
docs/sports-intelligence-providers.md
docs/sports-intelligence-admin-guide.md
docs/sports-intelligence-testing.md
```

## Database Migrations

New tables (reversible, no changes to existing tables):

- `sports_intelligence_sources`
- `sports_intelligence_items`
- `sports_experts`
- `sports_expert_predictions`
- `sports_expert_performance`
- `event_intelligence_consensus`

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ATLAS_EXPERT_INTELLIGENCE_ENABLED` | `false` in prod | Master feature flag |
| `ATLAS_INTELLIGENCE_LEARNING_MODE` | `observe` | `off` \| `observe` only |
| `ATLAS_MAX_EXPERT_CONFIDENCE_ADJUSTMENT` | `8` | Cap expert adj (pp) |
| `ATLAS_MAX_NEWS_CONFIDENCE_ADJUSTMENT` | `6` | Cap news adj (pp) |
| `ATLAS_MAX_TOTAL_INTELLIGENCE_ADJUSTMENT` | `12` | Total cap (pp) |

## Integration Points

1. **Post-scan hook** — after `SportsRefreshService.refresh_sports()` saves signals, optionally refresh intelligence for top picks (flagged).
2. **On-demand** — `GET /signals/sports/{id}/intelligence` reads cached consensus; never blocks on live fetch.
3. **Detail page** — `AtlasIntelligencePanel` loads cached intelligence asynchronously.
4. **Nightly job** — optional intelligence refresh for active signals (flagged).

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Breaks predictions | Intelligence is additive only; feature flag disables all paths |
| Slow detail page | Serve cached DB rows; refresh via separate endpoint |
| Copyright | Store summaries only; link to sources |
| Provider failures | Per-provider try/catch; mock fallback in dev |

## Rollback

1. Set `ATLAS_EXPERT_INTELLIGENCE_ENABLED=false`
2. UI hides intelligence sections automatically
3. Run down migration to drop new tables if needed
4. Remove router include from `main.py` (optional; disabled flag is sufficient)
