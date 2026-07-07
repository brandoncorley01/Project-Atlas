# Project Atlas — UI/UX Blueprint (Phase 7)

Wireframe descriptions for V1 screens. Dark theme recommended for trading dashboard feel.

---

## Global Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ [Atlas logo]  Dashboard  Options  Stocks  Sports  Parlays  News │  ← Top nav
│                                    Watchlist  Alerts  Performance│
├──────────────────────────────────────────────────────────────────┤
│ ⚠ Decision support only. Not financial advice. No guarantees.  │  ← Disclaimer strip
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│                        PAGE CONTENT                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

- **Desktop-first** with responsive collapse to hamburger menu on mobile
- **Score colors:** Green (high opportunity), Yellow (medium), Red (high risk warning)
- Every signal card shows all three scores prominently

---

## 1. Dashboard (Home)

```
┌─────────────────────────────────────────────────────────────────┐
│  Good morning, Brandon          Last refresh: 12 min ago  [↻]   │
├───────────────────────────────┬─────────────────────────────────┤
│  TOP 10 OPPORTUNITIES TODAY   │  BREAKING NEWS                  │
│  ┌─────────────────────────┐  │  • AAPL — Bullish — Impact 85   │
│  │ #1 Options AAPL Call    │  │  • Chiefs injury — Impact 72    │
│  │ Opportunity 88  Risk 32 │  │  • Fed speaker — Impact 60      │
│  └─────────────────────────┘  │                                 │
│  ┌─────────────────────────┐  ├─────────────────────────────────┤
│  │ #2 Sports NFL Chiefs ML │  │  QUICK PICKS                    │
│  └─────────────────────────┘  │  Best Options: [card mini]      │
│  ... (ranked list)            │  Best Stock:   [card mini]        │
│                               │  Best Sports:  [card mini]        │
│                               │  Best Parlay:  [card mini]        │
├───────────────────────────────┴─────────────────────────────────┤
│  WATCHLIST          │  RECENT ALERTS    │  PERFORMANCE (30D)      │
│  AAPL  NVDA  TSLA   │  3 unread         │  Win rate 58%  Avg +4.2% │
└─────────────────────────────────────────────────────────────────┘
```

**Interactions:**
- Click any opportunity → full signal detail
- "Last refresh" shows data staleness
- Unread alerts badge on nav

---

## 2. Options Signal Card

```
┌─────────────────────────────────────────────────────────────────┐
│  AAPL  CALL  $210  Jul 11 (12 DTE)              Opportunity 82  │
│  ─────────────────────────────────────────────────────────────  │
│  Premium $3.45   Spread 2.1%   Vol 12.5K   OI 45K               │
│  Δ 0.42   γ 0.08   θ -0.12   IV 28.5%                          │
├─────────────────────────────────────────────────────────────────┤
│  Confidence ████████░░ 78    Risk ███░░░░░░░ 35                 │
├─────────────────────────────────────────────────────────────────┤
│  RECOMMENDATION: Bullish call swing — breakout continuation      │
│  Entry: $3.20–$3.60  |  Targets: $4.50, $5.80  |  Max loss: $3.45│
│  Hold: 2–4 days                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Explanation]  [Bull case]  [Bear case]  [Invalidation]  tabs   │
├─────────────────────────────────────────────────────────────────┤
│  ⚠ RISK: Options can expire worthless. Defined risk at premium. │
├─────────────────────────────────────────────────────────────────┤
│  [Add to watchlist]  [Log outcome]  [Add note]    Updated 12m ago│
└─────────────────────────────────────────────────────────────────┘
```

**Chart area (expanded view):** TradingView Lightweight Chart for underlying with entry zone overlay.

---

## 3. Stock Signal Card

Similar layout to options, with:
- Ticker + current price header
- Entry range, stop loss, profit targets
- Technical summary row (RSI, RVOL, vs VWAP, trend)
- Sector/market context line

---

## 4. Sports Signal Card

```
┌─────────────────────────────────────────────────────────────────┐
│  NFL  Chiefs @ Bills  —  Moneyline Chiefs +145    Opp 75        │
│  ─────────────────────────────────────────────────────────────  │
│  Confidence 72  |  Risk 40  |  Est. EV +3.2%                    │
├─────────────────────────────────────────────────────────────────┤
│  Line moved: +130 → +145 (toward Chiefs)                        │
│  Injury: Bills CB questionable — Impact: Medium                 │
│  Weather: Clear, 42°F — Minimal impact                            │
├─────────────────────────────────────────────────────────────────┤
│  [Reasoning tabs]  |  ⚠ Gamble responsibly. Past ≠ future.      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Parlay Builder Page

```
┌─────────────────────────────────────────────────────────────────┐
│  CROSS-SPORT PARLAYS     [Conservative] [Balanced] [Aggressive] │
├─────────────────────────────────────────────────────────────────┤
│  PARLAY #1 — Balanced — Combined +450 — Opportunity 68          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Leg 1  MLB   Yankees ML -150      Reason: Ace starter     │   │
│  │ Leg 2  UFC   Fighter A ML -120    Reason: Style matchup   │   │
│  │ Leg 3  SOC   Over 2.5 +105        Reason: Both teams ATK  │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ⚠ Correlation warning: None detected across sports              │
│  Est. EV: +2.1%  |  Confidence 65  |  Risk 55                    │
├─────────────────────────────────────────────────────────────────┤
│  PARLAY #2 ...                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Filters:** Live now | Starting soon | Today | Next 72h

---

## 6. News Catalyst Board

```
┌─────────────────────────────────────────────────────────────────┐
│  NEWS CATALYST BOARD     Filter: [All] [Bullish] [Bearish]      │
│                        Min impact: [slider 50+]                  │
├─────────────────────────────────────────────────────────────────┤
│  🔴 BEARISH  Impact 88  Time-sensitive  AAPL, MSFT               │
│  CEO resignation at supplier — supply chain risk                 │
│  2 hours ago  |  Source: Reuters  |  [View]                      │
├─────────────────────────────────────────────────────────────────┤
│  🟢 BULLISH  Impact 75  TSLA                                   │
│  New product launch beats expectations                           │
└─────────────────────────────────────────────────────────────────┘
```

Click → side panel with full summary, related tickers, linked signals.

---

## 7. Watchlist

```
┌─────────────────────────────────────────────────────────────────┐
│  WATCHLIST                              [+ Add ticker/symbol]   │
├─────────────────────────────────────────────────────────────────┤
│  AAPL   $210.50  +1.2%   Latest signal: Call $210 — Opp 82     │
│  NVDA   $142.30  -0.5%   No active signal                      │
│  Chiefs ML  Next: Sun 4:25pm   Signal: Opp 75                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Performance Tracker

```
┌─────────────────────────────────────────────────────────────────┐
│  PERFORMANCE — Last 30 days                                     │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  Win rate    │  Avg return  │  Avg loss    │  Avg hold            │
│  58%         │  +12.4%      │  -8.2%       │  3.2 days            │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│  By module:  Options 62%  |  Stocks 55%  |  Sports 51%         │
│  Best strategy: Catalyst options (3-7 DTE)                        │
├─────────────────────────────────────────────────────────────────┤
│  SIGNAL HISTORY                                                  │
│  Date   Module   Signal        Outcome   Return   [Notes]       │
│  6/28   Options  AAPL Call     Win       +42%    "Great entry"  │
└─────────────────────────────────────────────────────────────────┘
```

**Log outcome modal:** Win / Loss / Scratch + return % + optional note.

---

## Design Tokens (V1)

| Token | Value |
|-------|-------|
| Background | `#0f1419` |
| Surface/card | `#1a2332` |
| Primary accent | `#3b82f6` |
| Success/opportunity | `#22c55e` |
| Warning | `#eab308` |
| Risk/danger | `#ef4444` |
| Text primary | `#f1f5f9` |
| Text muted | `#94a3b8` |
| Font | Geist Sans (already in Next.js template) |

---

## Auth Screens

**Login:** Email + password, Atlas branding, link to disclaimer.
**V1:** No public signup — account created in Supabase dashboard.
