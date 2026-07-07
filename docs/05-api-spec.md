# Project Atlas — API Specification (v1)

Base URL: `https://<api-host>/api/v1`  
Auth: `Authorization: Bearer <supabase_jwt>` on all protected routes.

---

## Health

### `GET /health`

Public. Returns API and job status.

**Response 200:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "connected",
  "last_jobs": {
    "refresh_options": "2026-06-29T14:30:00Z",
    "refresh_stocks": "2026-06-29T14:30:00Z",
    "refresh_sports": "2026-06-29T14:15:00Z",
    "refresh_news": "2026-06-29T14:10:00Z"
  }
}
```

---

## Dashboard

### `GET /dashboard`

Top opportunities and highlights for home screen.

**Query:** `limit` (default 10)

**Response 200:**
```json
{
  "top_opportunities": [/* mixed SignalSummary[] */],
  "best_options": {/* OptionsSignal */},
  "best_stock": {/* StockSignal */},
  "best_sports": {/* SportsSignal */},
  "best_parlay": {/* Parlay */},
  "breaking_news": [/* NewsItem[] */],
  "unread_alerts_count": 3,
  "performance_summary": {
    "win_rate_30d": 0.58,
    "avg_return_30d": 4.2
  }
}
```

---

## Signals — Options

### `GET /signals/options`

List options signals.

**Query:** `limit`, `offset`, `sort` (`opportunity_score`|`created_at`), `status` (`active`|`expired`|`all`)

### `GET /signals/options/{id}`

Single options signal with full detail.

### Shared signal response shape (options example):
```json
{
  "id": "uuid",
  "module": "options",
  "underlying": "AAPL",
  "option_type": "call",
  "strike": 210,
  "expiration": "2026-07-11",
  "days_to_expiration": 12,
  "premium": 3.45,
  "bid_ask_spread_pct": 2.1,
  "volume": 12500,
  "open_interest": 45000,
  "greeks": { "delta": 0.42, "gamma": 0.08, "theta": -0.12, "iv": 28.5 },
  "entry_zone": { "low": 3.2, "high": 3.6 },
  "profit_targets": [4.5, 5.8],
  "max_loss": 3.45,
  "expected_hold_time": "2-4 days",
  "scores": {
    "confidence": 78,
    "risk": 35,
    "opportunity": 82
  },
  "recommendation": "Bullish call swing on breakout continuation",
  "explanation": "...",
  "bull_case": "...",
  "bear_case": "...",
  "invalidation": "Close below $205 on daily",
  "suggested_action": "Enter on pullback to $3.20-$3.40",
  "risk_warning": "Options can expire worthless. Not financial advice.",
  "status": "active",
  "data_as_of": "2026-06-29T14:30:00Z",
  "created_at": "2026-06-29T14:30:00Z"
}
```

---

## Signals — Stocks

### `GET /signals/stocks`
### `GET /signals/stocks/{id}`

Same list/detail pattern as options.

---

## Signals — Sports

### `GET /signals/sports`

**Query:** `sport`, `limit`, `offset`, `sort`

### `GET /signals/sports/{id}`

---

## Parlays

### `GET /parlays`

**Query:** `style` (`conservative`|`balanced`|`aggressive`), `limit`

### `GET /parlays/{id}`

Includes `legs[]` with sport, event, selection, odds, leg_reason.

---

## Top Opportunities (cross-module)

### `GET /signals/top`

**Query:** `limit` (default 10), `modules` (comma-separated)

Returns unified ranked list across options, stocks, sports.

---

## News

### `GET /news`

**Query:** `limit`, `sentiment`, `ticker`, `min_impact`

### `GET /news/{id}`

---

## Watchlist

### `GET /watchlist`

Returns default watchlist with items.

### `POST /watchlist/items`

```json
{ "item_type": "ticker", "symbol": "AAPL", "metadata": {} }
```

### `DELETE /watchlist/items/{id}`

---

## Alerts

### `GET /alerts`

**Query:** `unread_only` (bool), `limit`

### `PATCH /alerts/{id}/read`

Mark single alert read.

### `POST /alerts/read-all`

Mark all alerts read.

---

## Performance

### `GET /performance/summary`

**Query:** `days` (default 30), `module`

### `GET /performance/history`

Paginated signal performance log.

### `POST /performance`

Log outcome for a signal.

```json
{
  "module": "options",
  "signal_id": "uuid",
  "outcome": "win",
  "return_pct": 42.5,
  "hold_duration_hours": 48
}
```

---

## Notes

### `GET /notes`

**Query:** `signal_id`, `module`

### `POST /notes`

```json
{ "module": "options", "signal_id": "uuid", "content": "Entered at $3.30" }
```

### `PATCH /notes/{id}`
### `DELETE /notes/{id}`

---

## Error responses

```json
{
  "detail": "Human-readable message",
  "code": "NOT_FOUND"
}
```

| Status | Code | When |
|--------|------|------|
| 401 | `UNAUTHORIZED` | Missing or invalid JWT |
| 403 | `FORBIDDEN` | Valid JWT, wrong user |
| 404 | `NOT_FOUND` | Resource missing |
| 422 | `VALIDATION_ERROR` | Bad request body |
| 500 | `INTERNAL_ERROR` | Server error |

---

## Internal / Admin (not exposed in V1)

Background jobs write signals via service role:
- `POST /internal/jobs/refresh-options` (cron + secret header)

These routes are protected by `X-Cron-Secret` env var, not user JWT.
