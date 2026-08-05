"""Versioned scoring formula registry."""

from __future__ import annotations

from typing import Any

OPTIONS_ACTIVITY_V1 = "options_activity_v1"
EXIT_V1 = "exit_v1"
WEATHER_V1 = "weather_v1"
EARNINGS_SETUP_V1 = "earnings_setup_v1"

OPTIONS_ACTIVITY_WEIGHTS: dict[str, float] = {
    "volume_oi": 0.22,
    "premium": 0.18,
    "spread": 0.12,
    "flow_class": 0.12,
    "repeat": 0.10,
    "delta": 0.08,
    "momentum": 0.08,
    "news": 0.05,
    "regime": 0.05,
}

EXIT_WEIGHTS: dict[str, float] = {
    "momentum": 0.18,
    "trend": 0.16,
    "volume": 0.10,
    "options": 0.12,
    "sector": 0.10,
    "market": 0.10,
    "thesis": 0.12,
    "reward_risk": 0.07,
    "event": 0.05,
}

WEATHER_WEIGHTS: dict[str, float] = {
    "index": 0.25,
    "breadth": 0.20,
    "sectors": 0.20,
    "options": 0.15,
    "volatility": 0.10,
    "news": 0.10,
}

EARNINGS_SETUP_WEIGHTS: dict[str, float] = {
    "expected_move": 0.22,
    "historical_move": 0.14,
    "liquidity": 0.16,
    "breakeven_reach": 0.16,
    "expected_value": 0.18,
    "sentiment_sector": 0.08,
    "iv_crush_risk": 0.06,
}

SCORE_CATALOG: dict[str, dict[str, Any]] = {
    "options_activity": {
        "version": OPTIONS_ACTIVITY_V1,
        "weights": OPTIONS_ACTIVITY_WEIGHTS,
        "summary": "Volume/OI, premium, spread, flow class, repeat, delta, momentum, news, regime",
    },
    "exit_urgency": {
        "version": EXIT_V1,
        "weights": EXIT_WEIGHTS,
        "summary": "Momentum, trend, volume, options, sector, market, thesis, R:R, event",
    },
    "market_weather": {
        "version": WEATHER_V1,
        "weights": WEATHER_WEIGHTS,
        "summary": "Index, breadth, sectors, options bias, volatility, news",
    },
    "earnings_setup": {
        "version": EARNINGS_SETUP_V1,
        "weights": EARNINGS_SETUP_WEIGHTS,
        "summary": "Expected move, historical move, liquidity, breakeven reach, EV after costs, sentiment/sector, IV crush",
    },
}


def get_score_meta(score_key: str) -> dict[str, Any]:
    meta = SCORE_CATALOG.get(score_key)
    if not meta:
        raise KeyError(f"Unknown score key: {score_key}")
    return meta


def list_score_versions() -> list[dict[str, Any]]:
    return [
        {
            "score_key": key,
            "version": meta["version"],
            "formula_summary": meta["summary"],
            "weights": meta["weights"],
            "active": True,
        }
        for key, meta in SCORE_CATALOG.items()
    ]
