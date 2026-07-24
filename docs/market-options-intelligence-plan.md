# Market & Options Intelligence — Implementation Plan

## Objective

Add Atlas-specific **Options Intelligence**, **Market Intelligence heatmaps**, and **swing-trade exit guidance** as decision-support features. Do not clone Unusual Whales / Finviz / TradingView. Do not auto-trade. Do not present simulated data as live.

## Existing Assets Reused

| Area | Files |
|------|--------|
| Options scan / Yahoo | `providers/options/yahoo.py`, `services/options_service.py` |
| Stock quotes / bars | `providers/stocks/*` |
| Universe / sectors | `providers/market/universe.py` |
| Market intelligence narrative | `services/market_intelligence_service.py` |
| Performance / outcomes | `services/performance_service.py`, `signal_performance` |
| Watchlist as position proxy | `watchlist_items` (no portfolio ledger yet) |
| Provider ABC pattern | `sports_intelligence/providers/base.py` |
| Auth / BFF | `dependencies.py`, `api/atlas/[...path]` |
| Nav | `AppNav.tsx`, `MobileBottomNav.tsx`, `ModuleNavStrip.tsx` |

## Smallest Safe Path

1. **Additive tables only** — no changes to `options_signals` / `stock_signals` schemas.
2. **New Python package** `app/market_intelligence/` with provider abstraction + versioned scores.
3. **Fixture / simulation provider** always available; live Yahoo delayed chain when reachable; never labeled live unless freshness says so.
4. **Watchlist-backed exit evaluations** — no new portfolio ledger in MVP.
5. **Feature flags** so pages can degrade gracefully when disabled.
6. **No paid-flow vendor hard-coupling** — interface + fixture + optional Yahoo-derived unusualness.

## Stages (this delivery)

| Stage | Scope |
|-------|--------|
| 1 | Models, migrations, freshness metadata, scoring-version framework, provider ABC + fixture |
| 2 | Options Intelligence API + UI tabs (flow, low-premium, smart-money, heatmap, history, performance, alerts) |
| 3 | Market Intelligence API + UI (heatmap, sector rotation, options bias, smart-money heatmap, weather, replay shell) |
| 4 | Exit urgency scoring + portfolio exit heatmap from watchlist/open signals |
| 5 | Signal outcome tracking hooks + analytics endpoints (basic) |

## New Surfaces

### Routes (web)

- `/options-intelligence` (+ tab query `?tab=`)
- `/market-intelligence` (+ tab query `?tab=`)

### API (`/api/v1/market-intelligence/...`)

- Options flow, low-premium, smart-money, signal detail/history/outcomes
- Heatmaps, sector rotation, market weather
- Position exit evaluation + portfolio exit heatmap
- Provider status / score versions

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ATLAS_MARKET_INTELLIGENCE_ENABLED` | `true` | Master flag |
| `ATLAS_OPTIONS_FLOW_PROVIDER` | `fixture` | `fixture` \| `yahoo_derived` |
| `ATLAS_OPTIONS_FLOW_ALLOW_SIMULATED` | `true` in development | Allow fixture in non-dev |
| `ATLAS_EXIT_SCORE_VERSION` | `exit_v1` | Exit formula version |
| `ATLAS_OPTIONS_SCORE_VERSION` | `options_activity_v1` | Unusual-activity formula version |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Fabricating “live” flow | Explicit `data_status` + badges; fixture always `simulated` |
| Breaking existing options | Separate nav section; reuse Yahoo only as delayed derivation |
| No portfolio ledger | Exit MVP evaluates watchlisted / active signals only |
| Score drift | Versioned formulas; store version on every score payload |
| Alert spam | Dedup keys + cooldowns in alert settings schema |

## Explicit Non-Goals (this milestone)

- Automatic order execution
- Claiming institutional identity
- Fabricating dark-pool prints
- Paid Unusual Whales / similar vendor integration (interface only)
- Replacing existing `/options` scan pipeline
