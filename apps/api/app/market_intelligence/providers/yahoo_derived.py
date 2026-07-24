"""Yahoo-derived unusualness from option chains (delayed, never labelled live)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.market_intelligence.normalization import normalize_activity
from app.market_intelligence.providers.base import OptionsFlowProvider
from app.market_intelligence.types import DataStatus, NormalizedOptionsActivity

logger = logging.getLogger(__name__)


class YahooDerivedFlowProvider(OptionsFlowProvider):
    """
    Derives unusual-looking contracts from Yahoo option chains.
    This is NOT tape-level options flow. Always delayed/historical status.
    """

    id = "yahoo_derived"
    name = "Yahoo Chain Unusualness (Delayed)"
    default_status = DataStatus.DELAYED

    def __init__(self, symbols: list[str] | None = None):
        self.symbols = symbols or ["AAPL", "NVDA", "MSFT", "SPY", "QQQ"]

    def is_enabled(self) -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except Exception:
            return False

    async def fetch_activity(self, params: dict[str, Any] | None = None) -> list[NormalizedOptionsActivity]:
        if not self.is_enabled():
            return []
        symbols = (params or {}).get("symbols") or self.symbols
        try:
            from app.providers.options.yahoo import fetch_options_candidates
        except Exception as exc:
            logger.warning("Yahoo derived provider unavailable: %s", exc)
            return []

        events: list[NormalizedOptionsActivity] = []
        now = datetime.now(UTC)
        for symbol in symbols[:8]:
            try:
                candidates = fetch_options_candidates(str(symbol), {"price": None})
            except Exception as exc:
                logger.debug("Yahoo chain fetch failed for %s: %s", symbol, exc)
                continue
            # Rank by volume vs OI when present
            ranked = sorted(
                candidates,
                key=lambda c: (getattr(c, "volume", 0) or 0) / max(getattr(c, "open_interest", 0) or 1, 1),
                reverse=True,
            )[:3]
            for idx, c in enumerate(ranked):
                vol = int(getattr(c, "volume", 0) or 0)
                oi = int(getattr(c, "open_interest", 0) or 0)
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
                    "underlying_price": getattr(c, "underlying_price", None),
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
                    events.append(normalized)
        return events
