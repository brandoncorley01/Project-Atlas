"""Profit-probability scoring — prefer developing ATM–OTM over already-ITM opens."""

from __future__ import annotations

from datetime import date, timedelta

from app.agents.analyst import _profit_probability_score, score_candidate
from app.engine.models import CandidateOpportunity, SignalModule


def _cand(**kwargs) -> CandidateOpportunity:
    defaults = dict(
        module=SignalModule.OPTIONS,
        symbol="TEST",
        option_type="put",
        strike=50.0,
        expiration=date.today() + timedelta(days=10),
        premium=0.55,
        bid=0.53,
        ask=0.55,
        volume=250,
        open_interest=2500,
        delta=0.35,
        relative_volume=1.5,
        has_catalyst=True,
        trend_bullish=False,
        metadata={"rsi": 45, "stock_price": 50.0},
    )
    defaults.update(kwargs)
    return CandidateOpportunity(**defaults)


def test_profit_prob_soft_caps_below_100():
    atm = _cand(strike=50.0, delta=0.42, metadata={"rsi": 45, "stock_price": 50.0})
    assert _profit_probability_score(atm) <= 92.0


def test_far_otm_put_not_near_97():
    # 12% OTM put with missing/low delta previously scored ~97–100.
    far = _cand(
        strike=44.0,
        delta=0.12,
        premium=0.20,
        bid=0.18,
        ask=0.20,
        metadata={"rsi": 45, "stock_price": 50.0},
    )
    prob = _profit_probability_score(far)
    assert prob < 85.0


def test_missing_delta_does_not_get_sweet_spot_bonus():
    lean = dict(
        has_catalyst=False,
        volume=80,
        open_interest=900,
        relative_volume=1.0,
        bid=0.50,
        ask=0.55,
        metadata={"rsi": 30, "stock_price": 50.0},
    )
    with_delta = _cand(delta=0.40, **lean)
    missing = _cand(delta=None, **lean)
    assert _profit_probability_score(missing) < _profit_probability_score(with_delta)
    assert _profit_probability_score(with_delta) < 92.0


def test_developing_otm_call_beats_already_itm_call():
    """Setups that still need the move should outrank strikes already ITM at open."""
    developing = _cand(
        option_type="call",
        strike=51.5,  # ~3% OTM
        delta=0.38,
        trend_bullish=True,
        metadata={
            "rsi": 52,
            "stock_price": 50.0,
            "previous_close": 49.5,
            "day_change_pct": 1.0,
        },
    )
    already_itm = _cand(
        option_type="call",
        strike=47.0,  # 6% ITM
        delta=0.68,
        trend_bullish=True,
        metadata={
            "rsi": 74,
            "stock_price": 50.0,
            "previous_close": 46.5,
            "day_change_pct": 7.5,
        },
    )
    assert _profit_probability_score(developing) > _profit_probability_score(already_itm)
    scored_dev = score_candidate(developing)
    scored_itm = score_candidate(already_itm)
    assert (scored_dev.scoring_snapshot or {}).get("entry_quality", 0) > (
        scored_itm.scoring_snapshot or {}
    ).get("entry_quality", 0)
