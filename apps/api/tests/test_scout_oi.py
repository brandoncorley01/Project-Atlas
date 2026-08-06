"""Scout liquidity gates — including Yahoo openInterest=0 volume proxy."""

from __future__ import annotations

from datetime import date, timedelta

from app.agents.scout import filter_candidates, open_interest_ok
from app.engine.models import CandidateOpportunity, SignalModule
from app.engine.pipeline import run_options_pipeline


def _cand(**overrides) -> CandidateOpportunity:
    base = dict(
        module=SignalModule.OPTIONS,
        symbol="AAPL",
        option_type="call",
        strike=210.0,
        expiration=date.today() + timedelta(days=14),
        premium=3.45,
        bid=3.40,
        ask=3.50,
        volume=4200,
        open_interest=1800,
        delta=0.42,
    )
    base.update(overrides)
    return CandidateOpportunity(**base)


def test_open_interest_ok_accepts_yahoo_zero_oi_with_volume():
    assert open_interest_ok(0, 4200) is True
    assert open_interest_ok(None, 4200) is True
    assert open_interest_ok(0, 20) is False
    assert open_interest_ok(80, 4200) is False  # known low OI still fails
    assert open_interest_ok(250, 10) is True


def test_scout_keeps_zero_oi_high_volume_live_candidates():
    liquid_yahoo = _cand(symbol="NVDA", open_interest=0, volume=8800, premium=2.10, bid=2.05, ask=2.15)
    illiquid = _cand(symbol="ILLIQ", open_interest=0, volume=12, premium=0.40, bid=0.30, ask=0.50)
    known_low_oi = _cand(symbol="LOWOI", open_interest=80, volume=500, premium=1.20, bid=1.15, ask=1.25)

    passed = filter_candidates([liquid_yahoo, illiquid, known_low_oi], strict=False)
    symbols = {c.symbol for c in passed}
    assert "NVDA" in symbols
    assert "ILLIQ" not in symbols
    assert "LOWOI" not in symbols


def test_options_pipeline_produces_signals_from_yahoo_zero_oi():
    cands = [
        _cand(symbol="AAPL", open_interest=0, volume=12500, has_catalyst=True, trend_bullish=True),
        _cand(symbol="MSFT", open_interest=0, volume=9000, premium=2.80, bid=2.70, ask=2.90),
    ]
    signals = run_options_pipeline(cands)
    assert signals, "pipeline should keep Yahoo OI=0 contracts when volume is strong"
    assert {s.planned.scored.candidate.symbol for s in signals} >= {"AAPL", "MSFT"}
