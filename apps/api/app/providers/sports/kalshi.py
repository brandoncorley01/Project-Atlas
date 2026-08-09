"""Kalshi public markets — crowd-implied game probabilities + short history."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app import config

logger = logging.getLogger(__name__)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Odds API sport_key → Kalshi game series ticker (moneyline-style binary markets).
SPORT_KEY_TO_SERIES: dict[str, str] = {
    "baseball_mlb": "KXMLBGAME",
    "baseball_mlb_preseason": "KXMLBSTGAME",
    "americanfootball_nfl": "KXNFLGAME",
    "americanfootball_nfl_preseason": "KXNFLGAME",
    "basketball_nba": "KXNBAGAME",
    "basketball_wnba": "KXWNBAGAME",
    "icehockey_nhl": "KXNHLGAME",
    "soccer_epl": "KXEPLGAME",
    "soccer_usa_mls": "KXMLSGAME",
    "soccer_spain_la_liga": "KXLALIGAGAME",
    "soccer_germany_bundesliga": "KXBUNDESLIGAGAME",
    "soccer_italy_serie_a": "KXSERIEAGAME",
    "soccer_france_ligue_one": "KXLIGUE1GAME",
    "americanfootball_ncaaf": "KXNCAAFGAME",
    "basketball_ncaab": "KXNCAABGAME",
    "mma_mixed_martial_arts": "KXUFCFIGHT",
    "boxing_boxing": "KXBOXINGFIGHT",
    "tennis_atp_french_open": "KXATPMATCH",
    "tennis_wta_french_open": "KXWTAMATCH",
    "tennis_atp_wimbledon": "KXATPMATCH",
    "tennis_wta_wimbledon": "KXWTAMATCH",
    "tennis_atp_us_open": "KXATPMATCH",
    "tennis_wta_us_open": "KXWTAMATCH",
}

# Sport label / slug fallbacks when sport_key is missing.
SPORT_LABEL_TO_SERIES: dict[str, str] = {
    "mlb": "KXMLBGAME",
    "baseball": "KXMLBGAME",
    "nfl": "KXNFLGAME",
    "football": "KXNFLGAME",
    "nba": "KXNBAGAME",
    "basketball": "KXNBAGAME",
    "wnba": "KXWNBAGAME",
    "nhl": "KXNHLGAME",
    "hockey": "KXNHLGAME",
    "epl": "KXEPLGAME",
    "mls": "KXMLSGAME",
    "la_liga": "KXLALIGAGAME",
    "laliga": "KXLALIGAGAME",
    "bundesliga": "KXBUNDESLIGAGAME",
    "serie_a": "KXSERIEAGAME",
    "ligue_1": "KXLIGUE1GAME",
    "ligue1": "KXLIGUE1GAME",
    "ncaaf": "KXNCAAFGAME",
    "ncaab": "KXNCAABGAME",
    "mma": "KXUFCFIGHT",
    "ufc": "KXUFCFIGHT",
    "boxing": "KXBOXINGFIGHT",
    "atp": "KXATPMATCH",
    "wta": "KXWTAMATCH",
    "tennis": "KXATPMATCH",
}

_STOP = {
    "the",
    "fc",
    "cf",
    "sc",
    "ac",
    "afc",
    "club",
    "city",
    "town",
    "united",
    "athletic",
}

# In-memory caches (single worker / process).
_events_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_candle_cache: dict[str, tuple[float, list[float]]] = {}
EVENTS_TTL_SEC = 600
CANDLES_TTL_SEC = 900


def series_for_sport(*, sport_key: str | None = None, sport: str | None = None) -> str | None:
    key = (sport_key or "").strip().lower()
    if key in SPORT_KEY_TO_SERIES:
        return SPORT_KEY_TO_SERIES[key]
    label = (sport or "").strip().lower().replace(" ", "_")
    if label in SPORT_KEY_TO_SERIES:
        return SPORT_KEY_TO_SERIES[label]
    hay = f"{key} {label} {(sport or '').strip().lower()}"
    for token, series in SPORT_LABEL_TO_SERIES.items():
        if token == label or token in label.split("_") or token in key.split("_"):
            return series
        if re.search(rf"\b{re.escape(token)}\b", hay):
            return series
    return None


def _tokens(name: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", (name or "").lower())
    out: set[str] = set()
    for t in raw:
        if len(t) < 2 or t in _STOP:
            continue
        out.add(t)
        if t.endswith("s") and len(t) > 3:
            out.add(t[:-1])
    return out


def _abbr(name: str, *, fallback: str = "??") -> str:
    text = (name or "").strip()
    if not text:
        return fallback
    # Prefer ticker-like trailing codes already short.
    if re.fullmatch(r"[A-Z]{2,4}", text):
        return text
    parts = [p for p in re.split(r"\s+", text) if p and p.lower() not in _STOP]
    if not parts:
        return text[:3].upper()
    if len(parts) == 1:
        return parts[0][:3].upper()
    # "Chicago C" / "New York" → first letters, capped.
    letters = "".join(p[0] for p in parts if p[0].isalnum())
    return (letters or parts[0][:3])[:4].upper()


def _dollars_to_pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    # Kalshi may return dollars ("0.54") or legacy cents (54).
    if n > 1.5:
        n = n / 100.0
    pct = max(0.0, min(100.0, n * 100.0))
    return round(pct, 1)


def _team_score(atlas_name: str, kalshi_name: str) -> float:
    a = _tokens(atlas_name)
    b = _tokens(kalshi_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    inter = a & b
    al = atlas_name.lower().strip()
    kl = kalshi_name.lower().strip()
    if not inter:
        # Substring fallback for "Padres" vs "San Diego Padres"
        if al and kl and (al in kl or kl in al):
            return 0.72
        return 0.0
    # Kalshi labels are short ("Toronto"); Atlas uses full names ("Toronto Blue Jays").
    # Score coverage of the shorter token set so city-only labels still match.
    shorter = min(len(a), len(b))
    longer = max(len(a), len(b))
    coverage = len(inter) / max(shorter, 1)
    jaccard = len(inter) / max(len(a | b), 1)
    score = max(coverage, jaccard)
    if b.issubset(a) or a.issubset(b):
        score = max(score, 0.85)
    if al and kl and (al in kl or kl in al):
        score = max(score, 0.72)
    # Tiny penalty when many unused tokens remain on the long name.
    if longer >= shorter + 2:
        score = min(1.0, score)
    return float(score)


def match_event(
    events: list[dict[str, Any]],
    *,
    home_team: str,
    away_team: str,
) -> dict[str, Any] | None:
    """Pick the Kalshi event whose two sides best match home/away names."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for event in events:
        markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
        if len(markets) < 2:
            continue
        # Prefer two-outcome game markets.
        sides = markets[:6]
        for i, m_a in enumerate(sides):
            for m_b in sides[i + 1 :]:
                name_a = str(m_a.get("yes_sub_title") or m_a.get("title") or "")
                name_b = str(m_b.get("yes_sub_title") or m_b.get("title") or "")
                # Orientation 1: A=away, B=home (Kalshi titles are often "Away vs Home")
                s1 = _team_score(away_team, name_a) + _team_score(home_team, name_b)
                # Orientation 2: swapped
                s2 = _team_score(away_team, name_b) + _team_score(home_team, name_a)
                score = max(s1, s2)
                if score > best_score:
                    best_score = score
                    orient = "away_home" if s1 >= s2 else "home_away"
                    best = {
                        "event": event,
                        "score": score,
                        "orient": orient,
                        "market_a": m_a if s1 >= s2 else m_b,
                        "market_b": m_b if s1 >= s2 else m_a,
                    }
    if not best or best_score < 1.1:
        return None
    return best


async def fetch_series_events(series_ticker: str, *, limit: int = 200) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _events_cache.get(series_ticker)
    if cached and now - cached[0] < EVENTS_TTL_SEC:
        return cached[1]

    url = f"{KALSHI_API_BASE}/events"
    params = {
        "limit": min(max(limit, 1), 200),
        "status": "open",
        "series_ticker": series_ticker,
        "with_nested_markets": "true",
    }
    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    events = [e for e in (payload.get("events") or []) if isinstance(e, dict)]
    _events_cache[series_ticker] = (now, events)
    return events


async def fetch_price_history(
    *,
    series_ticker: str,
    market_ticker: str,
    hours: int = 24,
    period_interval: int = 60,
) -> list[float]:
    cache_key = f"{market_ticker}:{hours}:{period_interval}"
    now = time.monotonic()
    cached = _candle_cache.get(cache_key)
    if cached and now - cached[0] < CANDLES_TTL_SEC:
        return cached[1]

    end_ts = int(time.time())
    start_ts = end_ts - max(hours, 1) * 3600
    url = (
        f"{KALSHI_API_BASE}/series/{series_ticker}/markets/{market_ticker}/candlesticks"
    )
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": period_interval,
    }
    timeout = httpx.Timeout(8.0, connect=4.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.info("Kalshi candlesticks skipped for %s: %s", market_ticker, exc)
        return []

    history: list[float] = []
    for candle in payload.get("candlesticks") or []:
        if not isinstance(candle, dict):
            continue
        price = candle.get("price") or {}
        pct = _dollars_to_pct(price.get("close_dollars") or price.get("mean_dollars"))
        if pct is None:
            pct = _dollars_to_pct((candle.get("yes_bid") or {}).get("close_dollars"))
        if pct is not None:
            history.append(pct)

    # Keep sparkline compact.
    if len(history) > 36:
        step = max(1, len(history) // 36)
        history = history[::step][-36:]
    _candle_cache[cache_key] = (now, history)
    return history


def _market_implied_pct(market: dict[str, Any]) -> float | None:
    for key in ("last_price_dollars", "yes_bid_dollars", "previous_yes_bid_dollars"):
        pct = _dollars_to_pct(market.get(key))
        if pct is not None:
            return pct
    # Legacy integer cents fields.
    for key in ("last_price", "yes_bid", "previous_yes_bid"):
        pct = _dollars_to_pct(market.get(key))
        if pct is not None:
            return pct
    return None


def build_pulse_from_match(
    match: dict[str, Any],
    *,
    series_ticker: str,
    selection: str | None,
    history_a: list[float] | None = None,
    history_b: list[float] | None = None,
) -> dict[str, Any]:
    event = match["event"]
    m_a = match["market_a"]
    m_b = match["market_b"]
    name_a = str(m_a.get("yes_sub_title") or m_a.get("title") or "Side A")
    name_b = str(m_b.get("yes_sub_title") or m_b.get("title") or "Side B")
    pct_a = _market_implied_pct(m_a)
    pct_b = _market_implied_pct(m_b)
    if pct_a is None and pct_b is not None:
        pct_a = round(100.0 - pct_b, 1)
    if pct_b is None and pct_a is not None:
        pct_b = round(100.0 - pct_a, 1)
    if pct_a is None or pct_b is None:
        return {}

    # Normalize mild vig so the two sides read as a clean public split.
    total = pct_a + pct_b
    if total > 0:
        pct_a = round(pct_a * 100.0 / total, 1)
        pct_b = round(100.0 - pct_a, 1)

    hist_a = list(history_a or [])
    hist_b = list(history_b or [])
    if hist_a and not hist_b:
        hist_b = [round(100.0 - p, 1) for p in hist_a]
    elif hist_b and not hist_a:
        hist_a = [round(100.0 - p, 1) for p in hist_b]
    if not hist_a:
        hist_a = [pct_a]
        hist_b = [pct_b]
    # Anchor sparkline end to the live print so labels and chart agree.
    if not hist_a or abs(hist_a[-1] - pct_a) >= 0.5:
        hist_a = [*hist_a, pct_a]
        hist_b = [*hist_b, pct_b]
    else:
        hist_a[-1] = pct_a
        hist_b[-1] = pct_b

    stance = _stance_vs_pick(selection, name_a, name_b, pct_a, pct_b)
    event_ticker = str(event.get("event_ticker") or "")
    return {
        "source": "kalshi",
        "series_ticker": series_ticker,
        "event_ticker": event_ticker,
        "title": str(event.get("title") or ""),
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "url": f"https://kalshi.com/markets/{event_ticker.lower()}" if event_ticker else None,
        "side_a": {
            "abbr": _abbr(name_a),
            "label": name_a,
            "implied_pct": pct_a,
            "market_ticker": m_a.get("ticker"),
        },
        "side_b": {
            "abbr": _abbr(name_b),
            "label": name_b,
            "implied_pct": pct_b,
            "market_ticker": m_b.get("ticker"),
        },
        "history_a": hist_a,
        "history_b": hist_b,
        "stance_vs_pick": stance,
    }


def _stance_vs_pick(
    selection: str | None,
    name_a: str,
    name_b: str,
    pct_a: float,
    pct_b: float,
) -> str | None:
    if not selection:
        return None
    score_a = _team_score(selection, name_a)
    score_b = _team_score(selection, name_b)
    if score_a < 0.35 and score_b < 0.35:
        # Try last token of selection (e.g. "Padres +1.5")
        sel_tokens = _tokens(selection)
        if not sel_tokens:
            return None
        score_a = len(sel_tokens & _tokens(name_a)) / max(1, len(sel_tokens))
        score_b = len(sel_tokens & _tokens(name_b)) / max(1, len(sel_tokens))
    if score_a < 0.2 and score_b < 0.2:
        return None
    pick_pct = pct_a if score_a >= score_b else pct_b
    if pick_pct >= 58:
        return "sure"
    if pick_pct <= 42:
        return "doubtful"
    return "mixed"


async def public_pulse_for_matchup(
    *,
    home_team: str,
    away_team: str,
    sport_key: str | None = None,
    sport: str | None = None,
    selection: str | None = None,
    include_history: bool = True,
) -> dict[str, Any] | None:
    """Resolve a Kalshi public-probability pulse for a home/away matchup."""
    if not config.settings.atlas_kalshi_public_pulse_enabled:
        return None
    if not home_team or not away_team:
        return None
    series = series_for_sport(sport_key=sport_key, sport=sport)
    if not series:
        return None
    try:
        events = await fetch_series_events(series)
    except Exception as exc:
        logger.info("Kalshi events fetch failed for %s: %s", series, exc)
        return None
    matched = match_event(events, home_team=home_team, away_team=away_team)
    if not matched:
        return None

    history_a: list[float] = []
    history_b: list[float] = []
    if include_history:
        m_a = matched["market_a"]
        m_b = matched["market_b"]
        ticker_a = str(m_a.get("ticker") or "")
        ticker_b = str(m_b.get("ticker") or "")
        if ticker_a:
            history_a = await fetch_price_history(series_ticker=series, market_ticker=ticker_a)
        if ticker_b and not history_a:
            history_b = await fetch_price_history(series_ticker=series, market_ticker=ticker_b)

    pulse = build_pulse_from_match(
        matched,
        series_ticker=series,
        selection=selection,
        history_a=history_a,
        history_b=history_b,
    )
    return pulse or None
