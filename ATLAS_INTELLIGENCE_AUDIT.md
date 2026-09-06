# Atlas Intelligence System Audit

**Date:** 2026-09-06  
**Scope:** Full repository (read-only analysis; no product code changes)  
**Goal:** Evolve Atlas into a stronger decision & prediction intelligence platform  
**Pillars:** Market Intelligence · Sports Intelligence (Premium Sports Picks = mission-critical)

---

## Executive Verdict

Atlas is a **working private decision platform** with a real scan→board→grade→calibrate flywheel — not a mockup.  
It is **not yet** a true prediction-intelligence system: edge is mostly **price disagreement**, “Premium” is **not a coded quality gate**, learning mostly **nudges thresholds**, and Market Intel often paints **delayed/fixture** data that looks complete.

**Lifecycle coverage (both pillars):**

| Step | Sports | Market |
|------|--------|--------|
| SCAN | SUPPORTED | SUPPORTED |
| DISCOVER | PARTIAL | SUPPORTED |
| BUILD THESIS | SUPPORTED | PARTIAL |
| CHALLENGE | PARTIAL | MISSING |
| RANK | SUPPORTED | SUPPORTED |
| WATCH | SUPPORTED | SUPPORTED |
| CONFIRM | PARTIAL | PARTIAL |
| TRACK OUTCOME | PARTIAL (ML/spread/total only) | PARTIAL (MI performance stub) |
| LEARN | PARTIAL (thresholds; SI observe-only) | PARTIAL (thresholds; earnings no auto-learn) |

---

## A. Current Atlas Architecture

```
apps/web (Next.js + BFF /api/atlas)  →  apps/api (FastAPI /api/v1)  →  Supabase (Auth + Postgres + RLS)
         ↑ jobs: apps/api/app/jobs/*  |  cron: render.yaml nightly_learning
```

**Two product pillars, multiple overlapping “intelligence” surfaces:**

| Layer | Path | Role |
|-------|------|------|
| Sports board | `services/sports_service.py`, `agents/sports_analyst.py`, `providers/sports/odds_api.py` | Odds → score → `sports_signals` |
| Atlas Insight | `services/sports_openai_picks_service.py` | FanDuel-catalog rank + optional LLM |
| Sports Expert Intel | `sports_intelligence/*` | RSS/manual consensus (observe mode) |
| Parlays | `agents/parlay_builder.py`, `services/parlay_service.py` | Combinatorics from board |
| Options engine | `services/options_service.py`, `engine/pipeline.py`, `agents/scout|analyst|planner` | Deep scan → `options_signals` |
| Stocks engine | `services/stock_service.py`, `agents/stock_analyst.py` | Swing setups → `stock_signals` |
| Market Intelligence desk | `market_intelligence/*`, `routers/market_intelligence.py` | Flow, ATS, congress, heatmaps, earnings |
| LLM “market intelligence” | `services/market_intelligence_service.py` | **Name collision** — narrative over performance, not the MI desk |
| Learning core | `signal_registry_service` → `outcome_resolver` → `performance_service` → `calibration_service` | Shared flywheel |
| Home repair | `dashboard_fix_service.py` | Fill empty boards + maintain |

**Primary data sources (verified):**

| Source | Used for | Notes |
|--------|----------|-------|
| The Odds API | Sports odds + scores | Default `ODDS_SPEND_MODE=cache_only`; FanDuel/DK as book keys |
| Yahoo / yfinance | Options chains, bars, earnings | Primary equities stack |
| Finnhub | Quotes, news, context | When keyed |
| FINRA ATS | Dark-pool weekly | Real, delayed |
| House PTR | Congress trades | Real when PDFs parse |
| RSS | Sports + market news | Keyword match |
| OpenAI | Insight polish, explain, search | Soft-fail paths |
| Kalshi public | Sports crowd % pulse | **Sports only**; does not score |
| Fixtures | MI flow/heatmaps client+server | Can look “live” |

**Not implemented despite docs:** API-Sports, dedicated weather/injury APIs, `packages/shared` types package (empty), `agents/coach.py`.

---

## B. What Atlas Already Does Well

1. **End-to-end sports pipeline** — fetch/cache → score → persist → UI → Insight → parlays → auto-grade core markets.  
2. **Credit-aware Odds usage** — cache/remote cache, spend modes, Repair/Fetch separation.  
3. **Board safety work** — insert-before-delete on sports/options/stocks; soft-fail surfacing; Fix-all sports-first.  
4. **Deterministic options scout/analyst/planner** with capital-first (`budget_first`) until proven win rate.  
5. **Shared learning flywheel** — registry → resolve → performance → calibration applied on next scan.  
6. **Watchlist + user Search bets** with origin split (Atlas vs user) in performance.  
7. **Earnings EV gates** — expected move, liquidity, AVOID/WATCH/MICRO_COATTAIL/QUALIFIED_TRADE.  
8. **Honest FINRA path** — empty on failure rather than inventing dark-pool prints.  
9. **BFF auth proxy** and long engine timeouts for heavy scans.  
10. **Domain depth** — sports categories, parlays, performance UI, coach narrative already shipped beyond early roadmap docs.

**Instinct:** KEEP the engines and learning core; IMPROVE quality gates and metrics.

---

## C. Premium Sports Picks Assessment

### Finding: “Premium” is mission language, not a coded gate

Repo search finds **no** `Premium Sports Picks`, `premium_pick`, or sports `is_premium`.  
“Premium” in code mostly means **options contract price**.

### What actually selects sports picks

| Mechanism | Reality | Path |
|-----------|---------|------|
| Edge | `(median_implied − best_implied) × 100` — cross-book gap | `agents/sports_analyst.py` |
| EV proxy | `edge × 0.85` (futures `× 0.7`) — not true fair-prob EV | same |
| Opportunity | `conf×0.5 + (100−risk)×0.3 + edge×4 + timing…` capped ~95 | same |
| Floors | Default edge ~0.6%, opp ~28; board `MIN_OPPORTUNITY=24`, target **120** picks | `sports_service.py`, `calibration_service.py` |
| Slate fill | `slate_mode` can drop edge to **0.25** or **0.0** for Today density | `sports_service.py` |
| Categories | Top Picks (top ~10), Steam (edge≥3.5%), Value (edge≥2%) | `sports_categories.py` |
| Insight | Separate FanDuel-catalog ranking + learning boost ±10 | `sports_openai_picks_service.py` |

### Honest quality judgment

| Claim | Verdict |
|-------|---------|
| Premium = hard quality certification | **FALSE** — relative ranking + soft floors |
| Edge = predictive edge vs true probability | **FALSE** — book disagreement; FD+DK alone often ~0 edge |
| Board always high-conviction | **FALSE** — slate mode admits near-zero-edge lines to fill Tonight |
| Props are first-class Premium | **WEAK** — postable via Insight; **not auto-gradable** |
| Matchup depth institutional | **WEAK** — last ~10 scores + RSS; no injuries/weather/lineups API |
| Kalshi improves pick quality | **NO** — display pulse only |

**Instinct:** BUILD a real Premium tier (hard gates + CLV + limited daily card). IMPROVE/CONSOLIDATE board as “Full Slate” vs “Premium.”

---

## D. Market Intelligence Assessment

### Real core (KEEP / IMPROVE)

- Options deep-scan + profit_probability heuristics (`agents/analyst.py`, scout gates OI/vol/spread).  
- Stock swings RSI/MACD/RVOL (`stock_analyst.py`) — usable, not TradingView-faithful (simple RSI; RVOL vs full history mean).  
- Earnings desk EV / expected move (`market_intelligence/earnings/*`).  
- News ingestion Finnhub + RSS → catalysts.  
- FINRA ATS + House congress when live.

### Weak / misleading (IMPROVE / CONSOLIDATE)

| Feature | Reality |
|---------|---------|
| Options “flow” | Default `yahoo_derived` = chain unusualness, **not** live tape |
| Smart money | Aggregation of same events; not institutional ID |
| Market weather | Heuristic from options bias; news_sentiment often None |
| Equity heatmap sizes | Hardcoded `_CAP_PROXY` market caps |
| MI performance / replay | **Stubs** — illustrative, not live track record |
| Client fixtures | Full UI with `simulated` when API fails — easy to over-trust |
| Kalshi for equities | **Missing** — sports only |
| Two MI services | Package desk vs LLM narrative — naming collision |

### Options vs Options Intelligence vs Stocks vs MI

Four overlapping idea surfaces for equities options/tech views → cognitive and trust debt.

**Instinct:** KEEP options/stock engines + earnings. CONSOLIDATE MI/OI desks. REMOVE/disable simulated paint in prod.

---

## E. Prediction / Confidence System

| Module | “Confidence” meaning | Calibration |
|--------|----------------------|-------------|
| Sports | Derived from setup strength, books, dampen — **not** calibrated win probability | Threshold nudges (edge/opp/dampen); sport/bet WR boost ±8 |
| Options | Heuristic profit_probability 0–92 + opportunity blend | Raise min prob/opp if mid bucket WR poor; budget_first until proven |
| Stocks | Opportunity from conf/risk/RVOL | Raise min opportunity if weak bucket fails |
| Parlays | `min(legs)×0.85 + avg×0.15` | Inherits soft board legs; weak correlation model |
| Expert SI | Caps ±8/±6/±12 on read | `learning_mode=observe` — outcome path effectively no-op |
| MI flow | unusual_score weights | Not linked to outcomes |

**Gaps:** No Brier/log-loss tracking; no probability calibration curves; no CLV; confidence ≠ P(win).

**Instinct:** IMPROVE labeling (“score” vs “win prob”). BUILD proper calibration metrics. BUILD Premium confidence gate.

---

## F. Learning & Performance Tracking

**Supported**

- `signal_performance`: win/loss/scratch/pending + `return_pct`  
- Sports unit-bet % (`unit_bet_return_pct` on $100 risk)  
- Stocks/options mark-style returns  
- Atlas vs user origin slicing  
- Coach aggregate + AI narrative  
- Nightly job: backfill → resolve → coach → LLM card  

**Missing / weak**

- Bankroll, stake-weighted ROI, Kelly/units ledger (stake on Search exists but not primary ledger)  
- CLV / closing line feedback  
- Props & futures auto-settlement (often scratched)  
- MI options-intel performance stub  
- Sports expert automatic learning (observe)  
- Multi-user cron (`DEFAULT_USER_ID`)  
- “Taken vs passed” decision journal  

**Instinct:** KEEP flywheel. IMPROVE metrics honesty in UI. BUILD units/CLV/journal + prop settlement.

---

## G. Redundant or Unnecessary Features

| Item | Instinct | Why |
|------|----------|-----|
| Market Intel + Options Intel + Home MI card + LLM “Market intelligence” | CONSOLIDATE | Four intel brands |
| Sports board Insight vs Analyst vs News vs Kalshi all-at-once | CONSOLIDATE | Card overload |
| Manual parlay on Sports vs `/parlays` | CONSOLIDATE | Two builders |
| Dual watchlist write paths (direct Supabase + API) | CONSOLIDATE | Drift risk |
| Client + server MI fixtures | CONSOLIDATE / REMOVE from prod | False confidence |
| `packages/shared` | REMOVE (until needed) | Empty |
| Stale roadmap “Milestone 0” docs | IMPROVE/archive | Misleading |
| Thin `coach_aggregate` wrapper | CONSOLIDATE | Job vs service |

---

## H. Broken / Incomplete / Disconnected Features

1. **No Premium Sports quality gate** — mission-critical gap.  
2. **`weather_impact: None`** placeholders; API-Sports documented but absent.  
3. **Props/futures** — postable, weak/ungradeable learning loop.  
4. **Sports SI observe mode** — adjustments computed; learning not closed.  
5. **MI performance & historical replay** — stubs.  
6. **Simulated options flow allowed** (`atlas_options_flow_allow_simulated=True`).  
7. **Default cache_only** — freshness depends on Fetch/Repair discipline.  
8. **BFF timeout vs scan quality** — long jobs skip polish; Fix-all still heavy.  
9. **Alerts** — in-app high-score + separate MI alert settings; thin wiring.  
10. **Docs lag** — architecture/API/folder/roadmap far behind shipped code.  
11. **RLS gaps** on some MI/earnings/odds-cache tables.  
12. **Line movement** stores scan snapshot — not true steam/CLV history.

---

## I. Highest-Impact Missing Capabilities

1. **Premium Sports card** — hard edge/CLV/liquidity/matchup gates; max N/day; separate from slate filler.  
2. **True decision journal** — taken/passed, stake, units, bankroll curve.  
3. **CLV / closing-line feedback** — sports edge truth.  
4. **Prop settlement + mark-to-market** — close Insight learning blind spot.  
5. **Unified Decision Brief (Home)** — stance + 3 actions + risk (fold MI + coach + boards).  
6. **Async scan/settle workers** — decouple quality from HTTP/BFF budgets.  
7. **Calibrated probabilities** — track reliability by sport/market/source.  
8. **Freshness SLA** — scheduled conservative live odds vs eternal cache.  
9. **Adversarial CHALLENGE step** — structured counter-thesis before rank.  
10. **MI trust layer** — live-only badges; hide/disable fixtures in production.

---

## J. Top 10 Recommended Improvements (by impact)

| # | Improvement | Instinct | Impact |
|---|-------------|----------|--------|
| 1 | Define & ship **Premium Sports Picks** (hard gates, daily limit, separate UI tier) | BUILD | Mission-critical trust |
| 2 | Add **CLV + units/stake journal**; relabel `return_pct` as unit P&L | BUILD / IMPROVE | Prediction truth |
| 3 | **Auto-grade props** (or stop promoting ungradable Insight props as core) | BUILD / CONSOLIDATE | Learning loop |
| 4 | **Consolidate Home** into one Decision Brief; demote secondary intel tabs | CONSOLIDATE | Actionability |
| 5 | Merge **Market Intel + Options Intel**; kill prod fixture paint | CONSOLIDATE / REMOVE | Trust |
| 6 | **Async workers** for scan/Insight/Fix-all/settlement | BUILD | Quality under timeouts |
| 7 | **Freshness policy** — scheduled live seed under spend lock; TTL vs SLA | IMPROVE | Sports edge freshness |
| 8 | Turn SI learning from **observe → automatic** (with caps) | IMPROVE | Sports feedback |
| 9 | Sports UI **progressive disclosure** (Premium / Tonight / Research) | CONSOLIDATE | Reduce overload |
| 10 | Regenerate **architecture/API docs** from code; archive Milestone-0 roadmap | IMPROVE | Operator clarity |

---

## K. Features to REMOVE or CONSOLIDATE

| Action | Target |
|--------|--------|
| **REMOVE** (prod path) | Client/server MI fixtures as default filled boards; simulated flow in production config |
| **REMOVE** (mental model) | Unused `packages/shared`; myth of `agents/coach.py` |
| **CONSOLIDATE** | Market Intel + Options Intel + Home MI promo + LLM MI card → one “Markets Desk” |
| **CONSOLIDATE** | Sports card chrome → Premium strip + expandable Research |
| **CONSOLIDATE** | Nav (11 items) → Decisions / Sports / Markets / Track / More |
| **CONSOLIDATE** | Dual watchlist writers → one API |
| **CONSOLIDATE** | Rename one of the two `MarketIntelligenceService` classes |
| **KEEP** | Odds pipeline, sports/options/stock engines, registry→grade→calibrate, watchlist, parlays (tighten gates), earnings EV, FINRA/congress when live |
| **IMPROVE** | Calibration depth, alerts wiring, RLS, docs, RSI/RVOL fidelity, parlay correlation |

---

## L. Recommended Atlas 2.0 Architecture

```
                    ┌─────────────────────────────────────┐
                    │         DECISION BRIEF (Home)         │
                    │  Premium Sports · Markets · Risks     │
                    └───────────────┬─────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ SPORTS INTEL     │      │ MARKET INTEL    │      │ TRACK & LEARN   │
│ Premium card     │      │ Options engine  │      │ Journal/units   │
│ Full slate       │      │ Swings          │      │ CLV + W/L       │
│ Insight/Research │      │ Earnings desk   │      │ Calibration     │
│ Parlays (gated)  │      │ Flow (live-only)│      │ Coach           │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  WORKERS: Scan · Settle · Learn      │
                    │  Providers: Odds · Yahoo · Finnhub   │
                    │  Store: signals · performance · cache│
                    └─────────────────────────────────────┘
```

**Lifecycle (enforce in product, not just code paths):**

`SCAN → DISCOVER → BUILD THESIS → CHALLENGE → RANK → WATCH → CONFIRM → TRACK OUTCOME → LEARN`

- **Premium Sports** must pass CHALLENGE + CONFIRM + hard RANK gates before Watch.  
- **Full Slate** can remain dense discovery.  
- **Markets Desk** shows live/delayed/simulated status as first-class trust chrome.  
- **Track** owns outcomes for both pillars with shared units language.

### Atlas 2.0 principle

> Atlas should stop optimizing for **board density** and optimize for **decision quality**: fewer Premium picks, harder gates, honest confidence, closed learning loops, and one place that tells the user what to do next.

---

## Appendix — Quick KEEP / IMPROVE / CONSOLIDATE / REMOVE / BUILD Map

| Area | Action |
|------|--------|
| Sports odds→board→parlay→grade (core markets) | KEEP |
| Slate-fill / near-zero edge posting | IMPROVE (isolate from Premium) |
| Premium Sports Picks product | BUILD |
| Atlas Insight | KEEP / IMPROVE (tie to Premium gates) |
| Sports Expert Intelligence | IMPROVE (exit observe) or CONSOLIDATE into Insight |
| Kalshi pulse | KEEP as research chrome; don’t score until validated |
| Options/stock engines | KEEP / IMPROVE |
| Earnings EV | KEEP |
| MI flow/smart-money/weather/perf stubs | CONSOLIDATE / REMOVE fixtures |
| Learning flywheel | KEEP / IMPROVE metrics |
| Units/CLV/journal | BUILD |
| Prop settlement | BUILD |
| Async workers | BUILD |
| Home/nav/intel surfaces | CONSOLIDATE |
| Docs | IMPROVE |
| packages/shared | REMOVE |

---

*End of audit. Verified against repository structure and primary services under `apps/api` and `apps/web` as of 2026-09-06. No application code was modified for this audit.*
