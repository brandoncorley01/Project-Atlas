"""Deterministic simulated options-activity fixture (always labelled simulated)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.market_intelligence.normalization import normalize_activity
from app.market_intelligence.providers.base import OptionsFlowProvider
from app.market_intelligence.types import DataStatus, NormalizedOptionsActivity


# Fixed fixture prints — deterministic for tests and UI empty-state demos.
_FIXTURE_ROWS: list[dict[str, Any]] = [
    {
        "underlying": "AAPL",
        "option_type": "call",
        "strike": 210,
        "expiration": "2026-08-21",
        "trade_timestamp": "2026-07-23T14:32:00+00:00",
        "contract_price": 3.45,
        "bid": 3.40,
        "ask": 3.50,
        "contracts": 850,
        "volume": 4200,
        "open_interest": 1800,
        "implied_volatility": 0.28,
        "delta": 0.42,
        "flow_class": "sweep",
        "open_close": "opening",
        "underlying_price": 208.5,
        "underlying_volume": 52_000_000,
        "sector": "Technology",
        "source_event_id": "fixture-aapl-call-1",
    },
    {
        "underlying": "AAPL",
        "option_type": "call",
        "strike": 215,
        "expiration": "2026-08-21",
        "trade_timestamp": "2026-07-23T14:45:00+00:00",
        "contract_price": 2.10,
        "bid": 2.05,
        "ask": 2.15,
        "contracts": 600,
        "volume": 3100,
        "open_interest": 1400,
        "implied_volatility": 0.29,
        "delta": 0.33,
        "flow_class": "sweep",
        "open_close": "opening",
        "underlying_price": 208.5,
        "sector": "Technology",
        "source_event_id": "fixture-aapl-call-2",
    },
    {
        "underlying": "NVDA",
        "option_type": "put",
        "strike": 120,
        "expiration": "2026-08-15",
        "trade_timestamp": "2026-07-23T15:10:00+00:00",
        "contract_price": 1.85,
        "bid": 1.80,
        "ask": 1.95,
        "contracts": 1200,
        "volume": 5500,
        "open_interest": 2200,
        "implied_volatility": 0.41,
        "delta": -0.38,
        "flow_class": "block",
        "open_close": "unknown",
        "underlying_price": 124.2,
        "sector": "Technology",
        "source_event_id": "fixture-nvda-put-1",
    },
    {
        "underlying": "XOM",
        "option_type": "call",
        "strike": 115,
        "expiration": "2026-09-18",
        "trade_timestamp": "2026-07-23T13:05:00+00:00",
        "contract_price": 0.95,
        "bid": 0.90,
        "ask": 1.05,
        "contracts": 400,
        "volume": 900,
        "open_interest": 2500,
        "implied_volatility": 0.22,
        "delta": 0.28,
        "flow_class": "standard",
        "open_close": "opening",
        "underlying_price": 112.0,
        "sector": "Energy",
        "source_event_id": "fixture-xom-call-1",
    },
    {
        "underlying": "JPM",
        "option_type": "put",
        "strike": 195,
        "expiration": "2026-08-21",
        "trade_timestamp": "2026-07-23T16:01:00+00:00",
        "contract_price": 2.40,
        "bid": 1.10,
        "ask": 3.80,
        "contracts": 50,
        "volume": 60,
        "open_interest": 40,
        "implied_volatility": 0.35,
        "delta": -0.12,
        "flow_class": "standard",
        "open_close": "unknown",
        "underlying_price": 205.0,
        "sector": "Financials",
        "source_event_id": "fixture-jpm-wide-1",
    },
    {
        "underlying": "SPY",
        "option_type": "call",
        "strike": 560,
        "expiration": "2026-08-01",
        "trade_timestamp": "2026-07-23T14:00:00+00:00",
        "contract_price": 4.20,
        "bid": 4.15,
        "ask": 4.25,
        "contracts": 2000,
        "volume": 15000,
        "open_interest": 8000,
        "implied_volatility": 0.15,
        "delta": 0.48,
        "flow_class": "sweep",
        "open_close": "opening",
        "underlying_price": 558.0,
        "sector": "Index",
        "source_event_id": "fixture-spy-call-1",
    },
]


class FixtureOptionsFlowProvider(OptionsFlowProvider):
    id = "fixture"
    name = "Atlas Fixture (Simulated)"
    default_status = DataStatus.SIMULATED

    def __init__(self, allow: bool = True):
        self._allow = allow

    def is_enabled(self) -> bool:
        return self._allow

    async def fetch_activity(self, params: dict[str, Any] | None = None) -> list[NormalizedOptionsActivity]:
        if not self.is_enabled():
            return []
        out: list[NormalizedOptionsActivity] = []
        for row in _FIXTURE_ROWS:
            # Keep relative timestamps fresh-ish but still simulated.
            payload = dict(row)
            payload["trade_timestamp"] = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
            payload["data_timestamp"] = payload["trade_timestamp"]
            normalized = normalize_activity(
                payload,
                data_source=self.id,
                data_status=DataStatus.SIMULATED,
            )
            if normalized:
                normalized.raw_metadata["simulated"] = True
                normalized.raw_metadata["disclaimer"] = (
                    "Simulated fixture data for development and testing. Not live market flow."
                )
                out.append(normalized)
        underlying = (params or {}).get("underlying")
        if underlying:
            u = str(underlying).upper()
            out = [e for e in out if e.underlying == u]
        return out
