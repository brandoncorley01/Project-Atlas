# Sports Intelligence Layer

Atlas collects authorized sports news, analyst context, and expert signals to enrich — not replace — the existing sports prediction model.

## Feature flag

Set in `apps/api/.env`:

```env
ATLAS_EXPERT_INTELLIGENCE_ENABLED=true
```

When `false`:

- Existing sports scans and picks behave unchanged
- Intelligence API routes return 404
- UI panels are hidden

Default is **on** in current code/`render.yaml` so analyst support can show under picks.

## Architecture

```
Providers (RSS, manual, mock)
  → Normalize → Dedupe → Store (Supabase)
  → Consensus → Bounded confidence adjustment
  → GET /signals/sports/{id}/intelligence (cached)
```

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/signals/sports/{id}/intelligence` | Cached intelligence payload |
| POST | `/api/v1/signals/sports/{id}/intelligence/refresh` | Async refresh |
| POST | `/api/v1/signals/sports/intelligence/manual` | Admin manual expert entry |
| GET | `/api/v1/signals/sports/intelligence/diagnostics` | Provider status |

## Database

Run migration `supabase/migrations/20250710000001_sports_intelligence.sql`.

## UI

`AtlasIntelligencePanel` on `/sports/[id]` shows recommendation, consensus, analyst cards, news, bull/bear, and verdict.

## Learning mode

`ATLAS_INTELLIGENCE_LEARNING_MODE=observe` stores observations only — no automatic weight changes.
