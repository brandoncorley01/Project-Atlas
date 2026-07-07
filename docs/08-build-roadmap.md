# Project Atlas — Build Roadmap (Phase 8)

Milestones from empty repo to daily-use V1. Build in order — each milestone is shippable.

---

## Milestone 0: Foundation ✅ (Current)

**Goal:** Monorepo, docs, skeleton apps, database schema defined.

| Item | Status |
|------|--------|
| Monorepo structure | Done |
| Docs (PRD → Roadmap) | Done |
| Next.js shell | Done |
| FastAPI shell | Done |
| Supabase migration SQL | Done |

**Testing:** `npm run dev` in apps/web shows dashboard shell; `uvicorn app.main:app` returns `/health`.

**Difficulty:** Easy

---

## Milestone 1: Auth & Database Live ✅

**Goal:** You can log in; profile and watchlist exist in Supabase.

| Item | Status |
|------|--------|
| Supabase project + migration | You completed |
| Login page | Done |
| Protected routes (middleware) | Done |
| JWT validation in FastAPI | Done |
| Sign out | Done |
| API `/me` and dashboard auth check | Done |

**Testing checklist:**
- [ ] `.env.local` and `apps/api/.env` filled in with Supabase keys
- [ ] Create user in Supabase dashboard (if not done)
- [ ] Login redirects to dashboard
- [ ] Unauthenticated users redirected to `/login`
- [ ] Dashboard shows "API connected" when backend is running
- [ ] Sign out works

Say **"start milestone 2"** when auth testing passes.

---

## Milestone 2: Opportunity Engine Core ✅

**Goal:** Scoring pipeline works on mock data; signals persist to DB.

| Item | Status |
|------|--------|
| CandidateOpportunity + Scout filter | Done |
| Analyst scoring (deterministic) | Done |
| Planner (entry/targets) | Done |
| Template explainer | Done |
| Persist to `options_signals` via Supabase | Done |
| `POST /api/v1/engine/run-mock` | Done |
| Dashboard + Options UI | Done |

**Try it:** Dashboard → **Generate mock signals** → see 3 ranked options (2 filtered as illiquid).

Say **"start milestone 3"** for real options data.

---

## Milestone 3: Options Module (Live Data) ✅

**Goal:** Real options signals from market data.

| Item | Status |
|------|--------|
| Yahoo Finance options chains (free) | Done |
| Finnhub stock quote/candles/news (optional key) | Done |
| Technical context (RSI, RVOL, trend) | Done |
| `POST /api/v1/engine/refresh-options` | Done |
| Watchlist symbols included in scan | Done |
| Dashboard "Refresh live options" button | Done |

**Data sources:**
- **Options chains:** Yahoo Finance (no key required)
- **Stock technicals + news:** Finnhub (add `FINNHUB_API_KEY` to `apps/api/.env` for richer scoring)

**Try it:** Dashboard → **Refresh live options** (works best during US market hours).

Say **"start milestone 4"** for the News Catalyst Engine.

---

## Milestone 4: News Catalyst Engine ✅

**Goal:** Breaking news on dashboard; news boosts signal scores.

**Features:**
- Finnhub + RSS ingestion
- News AI classification (sentiment, impact, tickers)
- `GET /news` API
- News board UI
- Catalyst boost in options/stock scoring

**Files:**
- `apps/api/app/providers/news/`
- `apps/api/app/agents/news_ai.py`
- `apps/api/app/jobs/refresh_news.py`
- `apps/web/src/app/(dashboard)/news/`

**Difficulty:** Medium

**Testing checklist:**
- [ ] News items have sentiment + impact score
- [ ] Tickers correctly linked
- [ ] High-impact news appears on dashboard
- [ ] Signal with catalyst shows higher confidence

---

## Milestone 5: Stock Swing Module ✅

**Goal:** Ranked stock swing signals with technicals.

| Item | Status |
|------|--------|
| Stock price provider + indicators | Done |
| `refresh_stocks` job | Done |
| Stock signal API + UI | Done |

Say **"start milestone 6"** for Sports Betting.

---

## Milestone 6: Sports Betting Module ✅

**Goal:** Moneyline, spread, O/U signals for major sports.

| Item | Status |
|------|--------|
| The Odds API adapter + multi-key failover | Done |
| FanDuel-first play line + multi-book odds per bet | Done |
| `refresh_sports` job | Done |
| Sports API + UI | Done |

---

## Milestone 7: Cross-Sport Parlay Builder ✅

**Goal:** Conservative/Balanced/Aggressive parlays across sports.

| Item | Status |
|------|--------|
| Parlay combinator + correlation warnings | Done |
| FanDuel combined pricing + per-leg multi-book odds | Done |
| `GET /parlays` API + UI | Done |

---

## Milestone 8: Alerts, Watchlist, Performance ✅

**Goal:** Full daily-use loop — watch, alert, track, learn.

| Item | Status |
|------|--------|
| Watchlist CRUD | Done |
| In-app alerts (high-score signal triggers) | Done |
| Performance logging (win/loss/scratch) | Done |
| Coach aggregate job | Done |
| Performance dashboard | Done |

**Try it:** Add tickers on **Watchlist** → run scans → check **Alerts** → log outcomes on **Performance**.

Say **"start milestone 9"** for UI/UX polish across the app.

---

## Milestone 9: UI/UX Polish & Readability ✅

**Goal:** More user-friendly, visually appealing, and easier to read across every feature.

| Item | Status |
|------|--------|
| FanDuel play-line + multi-book odds strip (sports & parlays) | Done |
| Consistent typography, spacing, and card hierarchy | Done |
| Score badges and module headers unified | Done |
| Empty states + loading skeletons | Done |
| Mobile nav and responsive layouts | Done |
| Readability pass (dashboard, options, stocks, sports, parlays, alerts, performance) | Done |
| Data Providers panel (Finnhub + Odds API gauges, multi-key credits) | Done |

**Scope:** Clear visual hierarchy on cards, scannable odds/EV blocks, better contrast for key actions, polished empty/error states, and a cohesive look from dashboard through detail pages.

**Delivered:** Design tokens in `globals.css`, shared `PageHeader` / `SectionHeader` / `EmptyState` / `Skeleton` / `StatusGauge` components, mobile bottom nav, unified score badges and FanDuel colors, loading skeletons on dashboard/sports/parlays, `DataProvidersPanel` with semicircle gauges and combined Odds API credit totals across failover keys.

Say **"start milestone 10"** when you're ready to deploy to production.

---

## Milestone 5 (legacy section): Stock Swing Module

**Goal:** Ranked stock swing signals with technicals.

**Features:**
- Stock price provider + indicator calculation
- `refresh_stocks` job
- Stock signal API + UI
- Mini chart on detail page (TradingView)

**Files:**
- `apps/api/app/providers/stocks/`
- `apps/api/app/jobs/refresh_stocks.py`
- `apps/web/src/components/charts/StockChart.tsx`

**Difficulty:** Medium

**Testing checklist:**
- [ ] RSI, MACD, RVOL computed correctly on sample ticker
- [ ] Entry/stop/targets reasonable vs price
- [ ] Stock signals ranked on dashboard

---

## Milestone 6 (legacy): Sports Betting Module

**Goal:** Moneyline, spread, O/U signals for major sports.

**Features:**
- The Odds API adapter
- Optional API-Sports for fixtures/injuries
- `refresh_sports` job
- Sports API + UI

**Files:**
- `apps/api/app/providers/sports/`
- `apps/api/app/jobs/refresh_sports.py`
- `apps/web/src/app/(dashboard)/sports/`

**Difficulty:** Medium-Hard

**Testing checklist:**
- [ ] Odds pulled for NFL/NBA/MLB
- [ ] Line movement tracked between refreshes
- [ ] Sports signal card shows EV estimate
- [ ] Injury/weather fields populated when data exists

---

## Milestone 7 (legacy): Cross-Sport Parlay Builder

**Goal:** Conservative/Balanced/Aggressive parlays across sports.

**Features:**
- Parlay combinator from top sports signals
- Correlation warnings (same-game, related events)
- `GET /parlays` API
- Parlay builder UI

**Files:**
- `apps/api/app/services/parlay_service.py`
- `apps/api/app/jobs/build_parlays.py`
- `apps/web/src/app/(dashboard)/parlays/`

**Difficulty:** Hard

**Testing checklist:**
- [ ] Parlays span 2+ sports
- [ ] Three style tiers differ in risk profile
- [ ] Each leg has reason text
- [ ] Correlation warning shows when applicable

---

## Milestone 8 (legacy detail): Alerts, Watchlist, Performance

**Goal:** Full daily-use loop — watch, alert, track, learn.

**Features:**
- Watchlist CRUD
- In-app alerts (threshold + price triggers)
- Performance logging (win/loss/scratch)
- Coach AI nightly aggregates
- Performance dashboard

**Files:**
- `apps/api/app/services/alert_service.py`
- `apps/api/app/services/performance_service.py`
- `apps/api/app/jobs/coach_aggregate.py`
- `apps/web/src/app/(dashboard)/alerts/`
- `apps/web/src/app/(dashboard)/watchlist/`
- `apps/web/src/app/(dashboard)/performance/`

**Difficulty:** Medium

**Testing checklist:**
- [ ] Add/remove watchlist items
- [ ] Alert fires when opportunity_score > threshold
- [ ] Log outcome updates performance summary
- [ ] 30-day win rate displays correctly

---

## Milestone 5: Stock Swing Module

**Goal:** Ranked stock swing signals with technicals.

**Features:**
- Stock price provider + indicator calculation
- `refresh_stocks` job
- Stock signal API + UI
- Mini chart on detail page (TradingView)

**Files:**
- `apps/api/app/providers/stocks/`
- `apps/api/app/jobs/refresh_stocks.py`
- `apps/web/src/components/charts/StockChart.tsx`

**Difficulty:** Medium

**Testing checklist:**
- [ ] RSI, MACD, RVOL computed correctly on sample ticker
- [ ] Entry/stop/targets reasonable vs price
- [ ] Stock signals ranked on dashboard

---

## Milestone 6: Sports Betting Module

**Goal:** Moneyline, spread, O/U signals for major sports.

**Features:**
- The Odds API adapter
- Optional API-Sports for fixtures/injuries
- `refresh_sports` job
- Sports API + UI

**Files:**
- `apps/api/app/providers/sports/`
- `apps/api/app/jobs/refresh_sports.py`
- `apps/web/src/app/(dashboard)/sports/`

**Difficulty:** Medium-Hard

**Testing checklist:**
- [ ] Odds pulled for NFL/NBA/MLB
- [ ] Line movement tracked between refreshes
- [ ] Sports signal card shows EV estimate
- [ ] Injury/weather fields populated when data exists

---

## Milestone 7: Cross-Sport Parlay Builder

**Goal:** Conservative/Balanced/Aggressive parlays across sports.

**Features:**
- Parlay combinator from top sports signals
- Correlation warnings (same-game, related events)
- `GET /parlays` API
- Parlay builder UI

**Files:**
- `apps/api/app/services/parlay_service.py`
- `apps/api/app/jobs/build_parlays.py`
- `apps/web/src/app/(dashboard)/parlays/`

**Difficulty:** Hard

**Testing checklist:**
- [ ] Parlays span 2+ sports
- [ ] Three style tiers differ in risk profile
- [ ] Each leg has reason text
- [ ] Correlation warning shows when applicable

---

## Milestone 8: Alerts, Watchlist, Performance

**Goal:** Full daily-use loop — watch, alert, track, learn.

**Features:**
- Watchlist CRUD
- In-app alerts (threshold + price triggers)
- Performance logging (win/loss/scratch)
- Coach AI nightly aggregates
- Performance dashboard

**Files:**
- `apps/api/app/services/alert_service.py`
- `apps/api/app/services/performance_service.py`
- `apps/api/app/jobs/coach_aggregate.py`
- `apps/web/src/app/(dashboard)/alerts/`
- `apps/web/src/app/(dashboard)/watchlist/`
- `apps/web/src/app/(dashboard)/performance/`

**Difficulty:** Medium

**Testing checklist:**
- [ ] Add/remove watchlist items
- [ ] Alert fires when opportunity_score > threshold
- [ ] Log outcome updates performance summary
- [ ] 30-day win rate displays correctly

---

## Milestone 10: Deploy to Production

**Goal:** Access from anywhere — Vercel + Render + Supabase.

**Features:**
- Environment variables configured
- CORS locked to production URL
- Cron jobs scheduled on Render
- Health monitoring
- Disable public Supabase signup

**Difficulty:** Medium

**Testing checklist:**
- [ ] Production login works
- [ ] Cron jobs run on schedule (check logs)
- [ ] No API keys in browser bundle
- [ ] HTTPS on all endpoints
- [ ] Disclaimer visible on first visit

---

## Milestone 11: Reliability & Daily Use

**Goal:** Reliable enough to check every morning.

**Features:**
- Error boundaries + empty states
- Loading skeletons
- Manual refresh button
- Signal history pagination
- Cost monitoring for APIs

**Difficulty:** Easy-Medium

---

## Estimated Timeline (Solo + AI assistance)

| Milestone | Est. time |
|-----------|-----------|
| M1 Auth & DB | 2–3 days |
| M2 Engine | 3–5 days |
| M3 Options | 5–7 days |
| M4 News | 2–3 days |
| M5 Stocks | 3–4 days |
| M6 Sports | 4–5 days |
| M7 Parlays | 3–4 days |
| M8 Alerts/Performance | 3–4 days |
| M9 UI/UX Polish | 3–5 days |
| M10 Deploy | 1–2 days |
| M11 Reliability | 2–3 days |

**Total V1:** ~6–10 weeks part-time

---

## What to Build Next

**Start Milestone 10:** Deploy to production — Vercel (web) + Render (API) + Supabase, with cron jobs, CORS, and health monitoring.

Say **"start milestone 10"** when you're ready to ship.
