"""Discover tradeable symbols beyond a fixed mega-cap list."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import yfinance as yf

logger = logging.getLogger(__name__)

# Always include liquid names with deep options markets.
CORE_LIQUID = [
    "AAPL", "NVDA", "MSFT", "AMZN", "META", "TSLA", "AMD", "GOOGL",
    "AVGO", "NFLX", "CRM", "UBER", "COIN", "PLTR", "SOFI", "INTC",
    "SPY", "QQQ", "IWM",
]

SCREENER_BUCKETS: list[tuple[str, int]] = [
    ("most_actives", 30),
    ("day_gainers", 20),
    ("day_losers", 20),
    ("undervalued_growth_stocks", 15),
    ("most_shorted_stocks", 10),
]


@dataclass
class DiscoveredSymbol:
    symbol: str
    sources: list[str] = field(default_factory=list)
    change_pct: float | None = None


def _extract_quotes(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        quotes = payload.get("quotes", [])
        return quotes if isinstance(quotes, list) else []
    return []


def _run_screener(query: str, count: int) -> list[dict]:
    try:
        return _extract_quotes(yf.screen(query, count=count))
    except Exception as exc:
        logger.warning("Screener %s failed: %s", query, exc)
        return []


def discover_market_symbols(*, max_symbols: int = 55) -> tuple[list[DiscoveredSymbol], dict]:
    """Pull movers, actives, and growth names from Yahoo screeners."""
    by_symbol: dict[str, DiscoveredSymbol] = {}
    stats: dict = {"screeners": {}, "total_raw": 0}

    for query, count in SCREENER_BUCKETS:
        quotes = _run_screener(query, count)
        stats["screeners"][query] = len(quotes)
        stats["total_raw"] += len(quotes)

        for row in quotes:
            sym = str(row.get("symbol", "")).upper().strip()
            if not sym or len(sym) > 5 or sym.endswith("-USD"):
                continue
            if sym not in by_symbol:
                by_symbol[sym] = DiscoveredSymbol(symbol=sym)
            entry = by_symbol[sym]
            if query not in entry.sources:
                entry.sources.append(query)
            change = row.get("regularMarketChangePercent") or row.get("percentChange")
            if change is not None:
                try:
                    entry.change_pct = float(change)
                except (TypeError, ValueError):
                    pass

    for sym in CORE_LIQUID:
        if sym not in by_symbol:
            by_symbol[sym] = DiscoveredSymbol(symbol=sym, sources=["core_liquid"])
        elif "core_liquid" not in by_symbol[sym].sources:
            by_symbol[sym].sources.append("core_liquid")

    ranked = sorted(
        by_symbol.values(),
        key=lambda s: (
            "core_liquid" in s.sources,
            "most_actives" in s.sources,
            abs(s.change_pct or 0),
        ),
        reverse=True,
    )

    selected = ranked[:max_symbols]
    stats["unique_discovered"] = len(by_symbol)
    stats["selected"] = len(selected)
    return selected, stats


def pre_score_symbol(entry: DiscoveredSymbol) -> float:
    """Fast symbol-level score before pulling full options chains."""
    score = 0.0
    sources = set(entry.sources)

    if "core_liquid" in sources:
        score += 30
    if "most_actives" in sources:
        score += 25
    if "day_gainers" in sources:
        score += 15
    if "day_losers" in sources:
        score += 12
    if "undervalued_growth_stocks" in sources:
        score += 10
    if "most_shorted_stocks" in sources:
        score += 8

    change = abs(entry.change_pct or 0)
    if change >= 3:
        score += 12
    elif change >= 1.5:
        score += 6

    return score
