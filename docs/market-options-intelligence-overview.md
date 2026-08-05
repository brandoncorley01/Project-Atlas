# Market & Options Intelligence — Overview

## What this is

Atlas decision-support for:

1. **Options Intelligence** — Flow Tracker (unusual options activity), FINRA dark-pool ATS volume, STOCK Act politician trade disclosures, low-premium opportunities, concentrated-activity watchlist, options bias heatmap, signal history, performance analytics, alert settings
2. **Market Intelligence** — **real equity stock market heatmap** (cap × daily %), sector rotation, options/smart-money heatmaps, Market Weather, portfolio exit heatmap, historical replay shell
3. **Swing-trade exit guidance** — explainable Exit Urgency Score with plain-English decision support (no auto-trading)

## What this is not

- Not a clone of Unusual Whales, Finviz, or TradingView
- Not automatic order execution
- Not institutional identity labeling
- Not fabricated live dark-pool prints (FINRA ATS is official but delayed)
- Not a claim that congressional trades are “smart money”

## Data status badges

Every response includes freshness metadata:

| Status | Meaning |
|--------|---------|
| `live` | True live provider (not used unless a live provider is configured and verified) |
| `delayed` | Yahoo-derived chain unusualness |
| `cached` | Reused recent payload |
| `historical` | Historical snapshot |
| `simulated` | Fixture / development data |
| `partial` | Incomplete inputs |

**Simulated, delayed, cached, and incomplete data are never presented as live.**

## Providers

| Provider | Env | Status |
|----------|-----|--------|
| `fixture` (default) | `ATLAS_OPTIONS_FLOW_PROVIDER=fixture` | Always `simulated` |
| `yahoo_derived` | `ATLAS_OPTIONS_FLOW_PROVIDER=yahoo_derived` | Always `delayed` |

Paid tape vendors are intentionally not hard-coupled. Add a new class under `app/market_intelligence/providers/` implementing `OptionsFlowProvider`.

## Score versions

| Key | Version | Purpose |
|-----|---------|---------|
| `options_activity` | `options_activity_v1` | Unusual options activity 0–100 |
| `exit_urgency` | `exit_v1` | Swing exit urgency 0–100 |
| `market_weather` | `weather_v1` | Regime / weather composite |

Every score payload includes version, weights, components, missing inputs, penalties, confidence, and data quality.

### Exit urgency bands

- 0–20 Strong Hold
- 21–40 Hold
- 41–55 Monitor Closely
- 56–70 Tighten Risk
- 71–85 Scale Out
- 86–100 Exit Review

## Routes

### Web

- `/options-intelligence`
- `/market-intelligence`

### API (`/api/v1/market-intelligence`)

- `GET /status`
- `GET /options/flow`
- `POST /options/low-premium`
- `GET /options/smart-money`
- `GET /options/heatmap`
- `GET /options/signals/history`
- `GET /options/performance`
- `GET /options/alerts/settings`
- `GET /heatmap` — equity stock market heatmap
- `GET /dark-pool` — FINRA ATS delayed dark-pool volume
- `GET /congress-trades` — House STOCK Act PTR disclosures
- `GET /sector-rotation`
- `GET /smart-money-heatmap`
- `GET /weather`
- `GET /replay`
- `POST /exit/evaluate`
- `POST /exit/portfolio-heatmap`
- `GET /weather`
- `GET /replay`
- `POST /exit/evaluate`
- `POST /exit/portfolio-heatmap`

## Migrations

- Up: `supabase/migrations/20250724000001_market_options_intelligence.sql`
- Down: `supabase/migrations/20250724000001_market_options_intelligence_down.sql`

Apply via your normal Supabase migration workflow. Additive only — no destructive changes to existing tables.

## Environment

```
ATLAS_MARKET_INTELLIGENCE_ENABLED=true
ATLAS_OPTIONS_FLOW_PROVIDER=fixture
ATLAS_OPTIONS_FLOW_ALLOW_SIMULATED=true
ATLAS_EXIT_SCORE_VERSION=exit_v1
ATLAS_OPTIONS_SCORE_VERSION=options_activity_v1
```

## Testing

```bash
cd apps/api
python -m pytest tests/test_market_intelligence.py -q
```

Tests are deterministic and do not require paid APIs.

## Known limitations

- Default provider is **simulated fixture** until a live/delayed tape provider is configured
- Portfolio Exit Heatmap uses **watchlist / open-signal proxies** (no full position ledger yet)
- Historical Replay schema is ready; full multi-day tape replay fills as snapshots accumulate
- Dark-pool inputs are omitted unless a legitimate configured provider supplies them
- Market Weather is regime context, not a forecast guarantee

## Disclaimers (product copy)

- Options activity does not prove intent.
- Large trades may be hedges or spread components.
- Heatmaps describe current or recent conditions and do not guarantee future movement.
- Exit guidance is decision support.
- Atlas does not guarantee returns.
- Data may be delayed, incomplete, or unavailable.
