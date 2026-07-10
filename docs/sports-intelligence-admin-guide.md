# Sports Intelligence Admin Guide

## Enable the layer

```env
ATLAS_EXPERT_INTELLIGENCE_ENABLED=true
ATLAS_INTELLIGENCE_LEARNING_MODE=observe
```

Restart the API after changing env vars.

## Manual expert entry

`POST /api/v1/signals/sports/intelligence/manual`

Admin access: `DEFAULT_USER_ID` match, or any user in `development`.

Body example:

```json
{
  "signal_id": "<sports_signal uuid>",
  "source": "Action Network",
  "analyst": "Jane Analyst",
  "source_url": "https://example.com/pick",
  "market_type": "spread",
  "selection": "Lakers -4.5",
  "line": -4.5,
  "odds": -110,
  "confidence": 72,
  "supporting_reasons": ["Home form", "Rest edge"],
  "risks": ["Injury uncertainty"],
  "published_at": "2026-07-10T18:00:00Z"
}
```

Delete: `DELETE /api/v1/signals/sports/intelligence/manual/{item_id}`

## Diagnostics

`GET /api/v1/signals/sports/intelligence/diagnostics`

Shows provider enablement, items ingested today, and last refresh time.

## Cron refresh

`POST /api/v1/internal/jobs/refresh-sports-intelligence`

Header: `X-Cron-Secret: <CRON_SECRET>`
