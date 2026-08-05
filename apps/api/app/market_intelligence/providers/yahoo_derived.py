"""Yahoo-derived unusualness from option chains (delayed, never labelled live)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.market_intelligence.normalization import normalize_activity
from app.market_intelligence.providers.base import OptionsFlowProvider
from app.market_intelligence.types import DataStatus, NormalizedOptionsActivity

logger = logging.getLogger(__name__)


def _candidates_for_symbol(symbol: str, price: float) -> list[Any]:
    from app.providers.options.yahoo import fetch_options_candidates

    if price <= 0:
        return []
    return fetch_options_candidates(symbol, {"price": price})


class YahooDerivedFlowProvider(OptionsFlowProvider):
    """
    Derives unusual-looking contracts from Yahoo option chains.
    This is NOT tape-level options flow. Always delayed/historical status.
    """

    id = "yahoo_derived"
    name = "Yahoo Chain Unusualness (Delayed)"
    default_status = DataStatus.DELAYED

    def __init__(self, symbols: list[str] | None = None):
        if symbols:
            self.symbols = symbols
        else:
            try:
                from app.providers.market.universe import CORE_LIQUID

                self.symbols = list(CORE_LIQUID)[:10]
            except Exception:
                self.symbols = ["AAPL", "NVDA", "MSFT", "SPY", "QQQ", "AMZN", "META", "TSLA"]

    def is_enabled(self) -> bool:
        try:
            import yfinance  # noqa: F401

            return True
        except Exception:
            return False

    async def fetch_activity(self, params: dict[str, Any] | None = None) -> list[NormalizedOptionsActivity]:
        if not self.is_enabled():
            return []
        symbols = list((params or {}).get("symbols") or self.symbols)[:10]
        try:
            from app.providers.stocks.quotes import fetch_stock_quotes
        except Exception as exc:
            logger.warning("Yahoo derived provider unavailable: %s", exc)
            return []

        quotes = await fetch_stock_quotes(symbols)
        now = datetime.now(UTC)
        events: list[NormalizedOptionsActivity] = []

        async def _one(symbol: str) -> list[NormalizedOptionsActivity]:
            q = quotes.get(symbol) or {}
            price = float(q.get("price") or 0)
            if price <= 0:
                return []
            try:
                candidates = await asyncio.to_thread(_candidates_for_symbol, str(symbol), price)
            except Exception as exc:
                logger.debug("Yahoo chain fetch failed for %s: %s", symbol, exc)
                return []
            ranked = sorted(
                candidates,
                key=lambda c: (getattr(c, "volume", 0) or 0) / max(getattr(c, "open_interest", 0) or 1, 1),
                reverse=True,
            )[:3]
            out: list[NormalizedOptionsActivity] = []
            for idx, c in enumerate(ranked):
                vol = int(getattr(c, "volume", 0) or 0)
                oi = int(getattr(c, "open_interest", 0) or 1)
                if vol < 50:
                    continue
                raw = {
                    "underlying": symbol,
                    "option_type": getattr(c, "option_type", "call"),
                    "strike": getattr(c, "strike", 0),
                    "expiration": getattr(c, "expiration", None),
                    "trade_timestamp": now.isoformat(),
                    "contract_price": getattr(c, "premium", None) or getattr(c, "ask", None),
                    "bid": getattr(c, "bid", None),
                    "ask": getattr(c, "ask", None),
                    "contracts": max(vol // 10, 1),
                    "volume": vol,
                    "open_interest": oi,
                    "implied_volatility": getattr(c, "implied_volatility", None),
                    "delta": getattr(c, "delta", None),
                    "flow_class": "standard",
                    "open_close": "unknown",
                    "underlying_price": price,
                    "source_event_id": f"yahoo-{symbol}-{idx}-{getattr(c, 'strike', 0)}",
                    "raw_metadata": {
                        "derived_from": "yahoo_option_chain",
                        "note": "Delayed chain unusualness — not live options tape / dark pool.",
                    },
                }
                if hasattr(raw["expiration"], "isoformat"):
                    raw["expiration"] = raw["expiration"].isoformat()
                normalized = normalize_activity(
                    raw,
                    data_source=self.id,
                    data_status=DataStatus.DELAYED,
                )
                if normalized:
                    out.append(normalized)
            return out

        # Bound concurrency so we stay under BFF budgets
        sem = asyncio.Semaphore(4)

        async def _guarded(sym: str) -> list[NormalizedOptionsActivity]:
            async with sem:
                return await _one(sym)

        batches = await asyncio.gather(*[_guarded(s) for s in symbols], return_exceptions=True)
        for batch in batches:
            if isinstance(batch, Exception):
                logger.debug("Yahoo derived batch error: %s", batch)
                continue
            events.extend(batch)
        return events
