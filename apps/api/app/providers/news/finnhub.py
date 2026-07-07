"""Finnhub market & company news ingestion."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.providers.stocks.finnhub import FinnhubClient, FinnhubError

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


async def fetch_market_news(*, limit: int = 50) -> list[dict[str, Any]]:
    if not settings.finnhub_api_key:
        return []
    try:
        client = FinnhubClient()
        data = await client._get("/news", {"category": "general"})
        if not isinstance(data, list):
            return []
        return [_normalize_finnhub(item, source="finnhub_market") for item in data[:limit]]
    except FinnhubError as exc:
        logger.warning("Finnhub market news failed: %s", exc)
        return []


async def fetch_company_news_batch(symbols: list[str], *, days: int = 2) -> list[dict[str, Any]]:
    if not settings.finnhub_api_key or not symbols:
        return []
    client = FinnhubClient()
    items: list[dict[str, Any]] = []
    for symbol in symbols[:20]:
        try:
            news = await client.get_company_news(symbol, days=days)
            for row in news[:8]:
                normalized = _normalize_finnhub(row, source="finnhub_company")
                normalized["hint_tickers"] = [symbol.upper()]
                items.append(normalized)
        except FinnhubError as exc:
            logger.info("Company news skip %s: %s", symbol, exc)
    return items


def _normalize_finnhub(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    ts = row.get("datetime")
    published = None
    if ts:
        try:
            published = datetime.fromtimestamp(int(ts), tz=UTC).isoformat()
        except (TypeError, ValueError):
            published = None

    return {
        "source": source,
        "title": str(row.get("headline") or row.get("title") or "").strip(),
        "url": row.get("url"),
        "summary": str(row.get("summary") or "")[:500],
        "published_at": published,
        "hint_tickers": [],
        "raw_payload": row,
    }
