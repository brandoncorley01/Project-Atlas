# Sports Intelligence Testing

## Unit tests

```bash
cd apps/api
pip install pytest
pytest tests/test_sports_intelligence.py tests/test_sports_intelligence_e2e.py -q
```

## Coverage areas

- Provider normalization
- Event/team matching (via existing `sports_news` matchers in RSS provider)
- Duplicate detection and syndicate grouping
- Consensus and expert weighting
- Confidence caps and labels
- Feature-flag default (disabled)

## Manual verification

1. Set `ATLAS_EXPERT_INTELLIGENCE_ENABLED=true` in `apps/api/.env`
2. Run migration `20250710000001_sports_intelligence.sql`
3. Run a sports scan or open an existing pick at `/sports/{id}`
4. Confirm **Atlas Intelligence** panel loads (empty state → Refresh)
5. Set flag to `false` — panel should not appear; sports list unchanged

## Rollback

1. `ATLAS_EXPERT_INTELLIGENCE_ENABLED=false`
2. Optional: run down migration (drop new tables in reverse order)
