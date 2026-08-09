# Project Atlas — Data Providers (Phase 6)

Recommendations prioritized for **low cost**, **personal-use scale**, and **V1 MVP quality**.

---

## Summary Table

| Data need | Recommended (V1) | Free tier | Paid fallback | Est. monthly cost |
|-----------|------------------|-----------|---------------|-------------------|
| Stock prices & bars | **Polygon.io** or **Finnhub** | Limited | Polygon Starter ~$29 | $0–29 |
| Options chains & Greeks | **Polygon.io** | Very limited | Polygon Options | $0–79 |
| Company news | **Finnhub** + **RSS** | Yes | Benzinga | $0 |
| SEC filings | **SEC EDGAR** (free API) | Yes | — | $0 |
| Macro calendar | **Finnhub** economic calendar | Yes | — | $0 |
| Sports odds | **The Odds API** | 500 req/mo | $30+ tiers | $0–30 |
| Sports stats/injuries | **API-Sports** or **ESPN unofficial** | Limited | API-Sports Pro | $0–15 |
| Weather (outdoor sports) | **OpenWeatherMap** | 1000 calls/day | — | $0 |
| Social sentiment | **Reddit API** + **Stocktwits** (optional) | Yes | — | $0 |
| LLM explanations | **OpenAI GPT-4o-mini** or **Claude Haiku** | Pay per use | — | $5–20 |

**Target V1 total:** ~$50–100/month if using one paid market data tier + odds API + LLM.

---

## 1. Stock Prices & Technicals

### Primary: Finnhub (free tier to start)

- **What:** Real-time/delayed quotes, daily candles, company profile
- **Why:** Generous free tier for personal use; simple REST API
- **Limits:** 60 calls/min on free — requires caching
- **Use for:** Stock swing module, underlying prices for options

### Upgrade: Polygon.io

- **What:** High-quality US equities, aggregates, snapshots
- **Why:** Better options integration when you upgrade
- **When:** Move here when options module needs reliable chain data

### Technical indicators

Compute in-house with **pandas-ta** or **ta-lib** on OHLCV from provider — avoids paying for pre-computed indicators.

---

## 2. Options Data (Highest Priority Module)

### Primary: Polygon.io Options

- **What:** Options chains, quotes, Greeks (on paid tiers)
- **Why:** Single vendor for stocks + options; good docs
- **V1 approach:** Start with Finnhub basic options if budget is $0; upgrade Polygon when signals need Greeks

### Alternative: Tradier (broker API)

- **What:** Options chains with Greeks for account holders
- **Why:** Free with brokerage account
- **Tradeoff:** Requires Tradier account; not ideal for SaaS later

### Filters (implemented in Scout AI, not provider):

- Min open interest: 500+
- Min volume: 100+ (or 50 for shorter DTE)
- Max bid/ask spread: 5–8%
- Max premium: configurable (e.g., $5 per contract)

---

## 3. News & Catalysts

### Layer 1: Finnhub Company News (free)

- News by symbol, general market news

### Layer 2: RSS feeds (free)

- Reuters, Bloomberg (where permitted), PR Newswire, SEC EDGAR Atom

### Layer 3: SEC EDGAR (free)

- 8-K, 10-Q, insider filings — high-signal catalysts

### News AI processing

- LLM classifies sentiment, impact, time sensitivity
- Map to tickers via NER + symbol lookup table

**Avoid for V1:** Expensive terminals (Benzinga Pro $$$, Bloomberg)

---

## 4. Sports Odds

### Primary: The Odds API (the-odds-api.com)

- **What:** Moneyline, spreads, totals from multiple books
- **Why:** Simple, affordable, covers NFL/NBA/MLB/NHL/soccer etc.
- **Free:** 500 requests/month — tight; cache aggressively
- **Paid:** ~$30/mo for hobby tier

### Line movement

- Store odds snapshots every refresh; compute movement in-house

### Sharp/public indicators

- **Kalshi public pulse (live):** Open Kalshi game markets via the public Trade API (no key). Matched to Atlas home/away, shown on sports cards as a dual-line crowd-probability sparkline (`public_market`). Flag: `ATLAS_KALSHI_PUBLIC_PULSE_ENABLED` (default on). Does not change scoring thresholds — decision aid only.
- **Also:** Coarse proxies from multi-book line movement
- **Later:** Action Network, betting splits (paid)

---

## 5. Sports Stats & Injuries

### Primary: API-Sports (api-sports.io)

- **What:** Fixtures, injuries, lineups for major sports
- **Why:** One API for many sports; reasonable pricing
- **Free tier:** Very limited — good for dev/testing

### Fallback: Manual curation for V1

- For MVP, injury impact can be LLM-assessed from news headlines if stats API is deferred

---

## 6. Weather

### OpenWeatherMap (free tier)

- **Use for:** NFL, MLB, soccer outdoor events
- **Input:** Venue city from event metadata
- **Impact:** Wind/rain flags fed into sports scoring

---

## 7. LLM Provider

### Recommended: OpenAI GPT-4o-mini

- **Use for:** News classification, signal explanations (structured JSON)
- **Why:** Cheap, fast, good JSON mode
- **Budget:** ~$5–15/mo at personal refresh cadence with caching

### Alternative: Anthropic Claude 3.5 Haiku

- Similar cost/quality for structured tasks

**Rule:** Never ask LLM to invent prices or Greeks — only explain provided structured data.

---

## 8. Provider Adapter Pattern (Backend)

Each provider lives in `apps/api/app/providers/<domain>/`:

```
providers/
├── stocks/finnhub.py
├── stocks/polygon.py
├── options/polygon.py
├── news/finnhub.py
├── news/rss.py
├── sports/odds_api.py
└── sports/api_sports.py
```

Interface example:
```python
class StockProvider(Protocol):
    async def get_quote(self, ticker: str) -> Quote: ...
    async def get_bars(self, ticker: str, timeframe: str) -> list[Bar]: ...
```

Swap providers via env config without changing scoring engine.

---

## 9. Caching Strategy (Cost Control)

| Data type | Cache TTL |
|-----------|-----------|
| Options chains | 15 min (market hours) |
| Stock quotes | 5–15 min |
| Sports odds | 10 min (game day) |
| News | 10 min |
| LLM explanations | 24h (same signal fingerprint) |

Use PostgreSQL or Redis later; V1 can use in-memory cache on single worker.

---

## 10. Recommended V1 Stack (Budget: ~$50/mo)

1. **Finnhub** — stocks + basic news (free)
2. **The Odds API** — sports odds (free tier → $30 if needed)
3. **OpenAI GPT-4o-mini** — explanations + news AI (~$10)
4. **OpenWeatherMap** — weather (free)
5. **SEC EDGAR + RSS** — catalysts (free)
6. **Render/Railway + Vercel + Supabase** — hosting (free tiers to start)

**First paid upgrade when ready:** Polygon.io for options chains + Greeks.
