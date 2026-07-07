"""Daily OHLCV bars for stock swing analysis and charts."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _yahoo_symbol(symbol: str) -> str:
    return symbol.upper().replace(".", "-")


def _fetch_yahoo_bars_sync(symbol: str, days: int = 120) -> dict[str, Any]:
    import yfinance as yf

    yahoo_sym = _yahoo_symbol(symbol)
    hist = yf.Ticker(yahoo_sym).history(period=f"{days}d", interval="1d")
    if hist is None or hist.empty:
        return {"symbol": symbol.upper(), "bars": []}

    bars: list[dict[str, Any]] = []
    for idx, row in hist.iterrows():
        bars.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": float(row["Volume"]),
            }
        )
    return {"symbol": symbol.upper(), "bars": bars}


async def fetch_daily_bars(symbol: str, *, days: int = 120) -> dict[str, Any]:
    """Fetch daily bars — Yahoo primary (Finnhub candles blocked on free tier)."""
    return await asyncio.to_thread(_fetch_yahoo_bars_sync, symbol, days)


def bars_to_series(bars: list[dict[str, Any]]) -> dict[str, list[float]]:
    return {
        "closes": [float(b["close"]) for b in bars],
        "highs": [float(b["high"]) for b in bars],
        "lows": [float(b["low"]) for b in bars],
        "volumes": [float(b["volume"]) for b in bars],
    }
