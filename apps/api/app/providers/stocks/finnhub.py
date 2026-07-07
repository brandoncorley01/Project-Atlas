from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.agents.news_ai import classify_headlines
from app.providers.technicals import compute_rsi, compute_sma, relative_volume

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


class FinnhubError(Exception):
    pass


class FinnhubClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.finnhub_api_key
        if not self.api_key:
            raise FinnhubError("FINNHUB_API_KEY is not configured")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = {"token": self.api_key, **(params or {})}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{FINNHUB_BASE}{path}", params=query)

        if response.status_code != 200:
            raise FinnhubError(f"Finnhub {path} failed: {response.status_code} {response.text}")

        return response.json()

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        return await self._get("/quote", {"symbol": symbol.upper()})

    async def get_daily_candles(self, symbol: str, days: int = 60) -> dict[str, list[float]]:
        now = int(datetime.now(UTC).timestamp())
        start = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
        data = await self._get(
            "/stock/candle",
            {"symbol": symbol.upper(), "resolution": "D", "from": start, "to": now},
        )
        if data.get("s") != "ok":
            return {"closes": [], "volumes": []}
        return {"closes": data.get("c", []), "volumes": data.get("v", [])}

    async def get_company_news(self, symbol: str, days: int = 2) -> list[dict[str, Any]]:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        data = await self._get(
            "/company-news",
            {"symbol": symbol.upper(), "from": start.isoformat(), "to": end.isoformat()},
        )
        return data if isinstance(data, list) else []

    async def get_stock_context(self, symbol: str) -> dict[str, Any]:
        """Quote + technical context for scoring. Degrades gracefully on free-tier limits."""
        quote = await self.get_quote(symbol)
        candles = await self._get_daily_bars(symbol)
        news = await self._safe_company_news(symbol)

        closes = candles["closes"]
        volumes = candles["volumes"]
        rsi = compute_rsi(closes)
        sma20 = compute_sma(closes, 20)
        price = float(quote.get("c") or 0)
        rvol = relative_volume(volumes) if volumes else 1.0
        trend_bullish = price > (sma20 or 0) and (rsi or 50) < 72
        catalyst = classify_headlines(news, {symbol.upper()}, primary_symbol=symbol.upper())
        top_headline = catalyst.get("top_headline")

        return {
            "price": price,
            "rsi": rsi,
            "sma20": sma20,
            "relative_volume": rvol,
            "trend_bullish": trend_bullish,
            "has_catalyst": bool(top_headline),
            "news_count": catalyst.get("news_count", len(news)),
            "top_headline": top_headline,
            "catalyst_impact": catalyst.get("catalyst_impact", 0),
            "catalyst_sentiment": catalyst.get("catalyst_sentiment"),
            "data_source": "finnhub",
        }

    async def _safe_company_news(self, symbol: str) -> list[dict[str, Any]]:
        try:
            return await self.get_company_news(symbol)
        except FinnhubError as exc:
            logger.warning("Finnhub news unavailable for %s: %s", symbol, exc)
            return []

    async def _get_daily_bars(self, symbol: str, days: int = 60) -> dict[str, list[float]]:
        try:
            return await self.get_daily_candles(symbol)
        except FinnhubError as exc:
            logger.info("Finnhub candles unavailable for %s (%s); using Yahoo fallback", symbol, exc)
            return await _yahoo_daily_bars(symbol, days)


async def _yahoo_daily_bars(symbol: str, days: int = 60) -> dict[str, list[float]]:
    def _fetch() -> dict[str, list[float]]:
        import yfinance as yf

        hist = yf.Ticker(symbol.upper()).history(period=f"{days}d")
        if hist.empty:
            return {"closes": [], "volumes": []}
        return {
            "closes": [float(v) for v in hist["Close"].tolist()],
            "volumes": [float(v) for v in hist["Volume"].tolist()],
        }

    return await asyncio.to_thread(_fetch)
