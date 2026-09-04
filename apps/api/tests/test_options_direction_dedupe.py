"""Read-path options board collapses call+put on the same expiry."""

from __future__ import annotations

from app.services.signal_service import _dedupe_options_rows


def _row(
    *,
    underlying: str,
    option_type: str,
    strike: float,
    expiration: str,
    confidence: float,
    opportunity: float = 55.0,
    profit_probability: float = 55.0,
    premium: float = 0.5,
):
    return {
        "underlying": underlying,
        "option_type": option_type,
        "strike": strike,
        "expiration": expiration,
        "confidence_score": confidence,
        "risk_score": 40.0,
        "opportunity_score": opportunity,
        "premium": premium,
        "delta": 0.3 if option_type == "call" else -0.3,
        "bid": premium - 0.02,
        "ask": premium + 0.02,
        "scoring_snapshot": {
            "profit_probability": profit_probability,
            "contract_cost": premium * 100,
        },
    }


def test_dedupe_options_keeps_confident_direction_and_nests_hedge():
    call = _row(
        underlying="SOFI",
        option_type="call",
        strike=18.0,
        expiration="2026-08-22",
        confidence=74,
        profit_probability=62,
    )
    put = _row(
        underlying="SOFI",
        option_type="put",
        strike=17.0,
        expiration="2026-08-22",
        confidence=61,
        profit_probability=54,
        premium=0.4,
    )
    out = _dedupe_options_rows([call, put])
    assert len(out) == 1
    primary = out[0]
    assert primary["option_type"] == "call"
    hedge = primary["scoring_snapshot"]["hedge_strategy"]
    assert hedge["option_type"] == "put"
    assert hedge["strike"] == 17.0


def test_dedupe_options_allows_different_expiries():
    a = _row(
        underlying="SOFI",
        option_type="call",
        strike=18.0,
        expiration="2026-08-22",
        confidence=70,
    )
    b = _row(
        underlying="SOFI",
        option_type="put",
        strike=17.0,
        expiration="2026-08-29",
        confidence=68,
    )
    out = _dedupe_options_rows([a, b])
    assert len(out) == 2
