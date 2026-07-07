"""Batch stock quotes for news cards and dashboards."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

YAHOO_CHUNK = 25


def _yahoo_symbol(symbol: str) -> str:
    """Yahoo uses dashes for class shares (e.g. BRK-B)."""
    return symbol.upper().replace(".", "-")


def _read_fast_info(ticker: Any) -> dict[str, float]:
    fast = getattr(ticker, "fast_info", None)
    if fast is None:
        return {}

    def _num(key: str, attr: str | None = None) -> float:
        value = None
        if hasattr(fast, "get"):
            value = fast.get(key)
        if value is None and attr:
            value = getattr(fast, attr, None)
        if value is None:
            value = getattr(fast, key, None)
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    price = _num("lastPrice", "last_price") or _num("regularMarketPrice", "regular_market_price")
    prev = _num("previousClose", "previous_close") or _num("regularMarketPreviousClose", "regular_market_previous_close")
    change = _num("regularMarketChange", "regular_market_change")
    change_pct = _num("regularMarketChangePercent", "regular_market_change_percent")

    if change == 0 and price and prev:
        change = price - prev
    if change_pct == 0 and prev > 0:
        change_pct = (change / prev) * 100

    if price <= 0:
        return {}

    return {
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
    }


def _quote_from_history(ticker: Any) -> dict[str, float]:
    try:
        hist = ticker.history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return {}
        price = float(hist["Close"].iloc[-1])
        if price <= 0:
            return {}
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        change = price - prev
        change_pct = (change / prev) * 100 if prev else 0.0
        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception as exc:
        logger.debug("History quote failed: %s", exc)
        return {}


def _yahoo_quote_single(symbol: str) -> dict[str, float]:
    import yfinance as yf

    yahoo_sym = _yahoo_symbol(symbol)
    try:
        ticker = yf.Ticker(yahoo_sym)
        quote = _read_fast_info(ticker)
        if quote:
            return quote
        return _quote_from_history(ticker)
    except Exception as exc:
        logger.debug("Yahoo single quote %s failed: %s", symbol, exc)
        return {}


def _fetch_yahoo_quotes_sync(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}

    import yfinance as yf

    unique = list(dict.fromkeys(s.upper() for s in symbols if s))
    out: dict[str, dict[str, Any]] = {}

    for i in range(0, len(unique), YAHOO_CHUNK):
        chunk = unique[i : i + YAHOO_CHUNK]
        yahoo_chunk = [_yahoo_symbol(sym) for sym in chunk]
        try:
            tickers = yf.Tickers(" ".join(yahoo_chunk))
            for original, yahoo_sym in zip(chunk, yahoo_chunk, strict=True):
                try:
                    ticker = tickers.tickers.get(yahoo_sym) or tickers.tickers.get(original)
                    if ticker is None:
                        continue
                    quote = _read_fast_info(ticker) or _quote_from_history(ticker)
                    if quote:
                        out[original] = quote
                except Exception as exc:
                    logger.debug("Yahoo chunk quote skip %s: %s", original, exc)
        except Exception as exc:
            logger.warning("Yahoo batch quote chunk failed: %s", exc)

    for sym in unique:
        if sym in out:
            continue
        quote = _yahoo_quote_single(sym)
        if quote:
            out[sym] = quote

    return out


async def _fetch_finnhub_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols or not settings.finnhub_api_key:
        return {}

    from app.providers.stocks.finnhub import FinnhubClient, FinnhubError

    client = FinnhubClient()
    out: dict[str, dict[str, Any]] = {}
    sem = asyncio.Semaphore(8)

    async def _one(symbol: str) -> None:
        async with sem:
            try:
                data = await client.get_quote(symbol)
                price = float(data.get("c") or 0)
                if price <= 0:
                    return
                change = float(data.get("d") or 0)
                change_pct = float(data.get("dp") or 0)
                out[symbol.upper()] = {
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                }
            except FinnhubError as exc:
                logger.debug("Finnhub quote skip %s: %s", symbol, exc)

    await asyncio.gather(*[_one(sym) for sym in symbols])
    return out


def _fetch_quotes_sync(symbols: list[str]) -> dict[str, dict[str, Any]]:
    return _fetch_yahoo_quotes_sync(symbols)


async def fetch_stock_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(s.upper() for s in symbols if s))
    if not unique:
        return {}

    yahoo = await asyncio.to_thread(_fetch_yahoo_quotes_sync, unique)
    missing = [sym for sym in unique if sym not in yahoo]
    if missing:
        finnhub = await _fetch_finnhub_quotes(missing)
        yahoo.update(finnhub)
    return yahoo
