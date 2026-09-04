"""Options persistence selection — directional primary + hedge + diversity."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.options_service import (
    MAX_PER_SYMBOL,
    MAX_SIGNALS_STORED,
    select_signals_to_save,
)


def _signal(
    symbol: str,
    strike: float,
    *,
    option_type: str = "call",
    dte: int = 14,
    confidence: float = 60.0,
    opportunity: float = 55.0,
    profit_probability: float = 55.0,
    premium: float = 0.50,
):
    candidate = SimpleNamespace(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiration=date.today() + timedelta(days=dte),
        premium=premium,
        delta=0.35 if option_type == "call" else -0.35,
        bid=premium - 0.02,
        ask=premium + 0.02,
    )
    scored = SimpleNamespace(
        candidate=candidate,
        confidence_score=confidence,
        risk_score=40.0,
        opportunity_score=opportunity,
        scoring_snapshot={
            "profit_probability": profit_probability,
            "contract_cost": round(premium * 100, 2),
            "is_budget": premium * 100 <= 100,
        },
    )
    planned = SimpleNamespace(scored=scored)
    return SimpleNamespace(planned=planned)


def test_select_signals_dedupes_identical_contracts():
    a = _signal("SOFI", 18.0, confidence=70)
    dup = _signal("SOFI", 18.0, confidence=70)
    b = _signal("SOFI", 19.0, confidence=65, dte=21)
    saved = select_signals_to_save([a, dup, b], limit=10, max_per_symbol=5)
    keys = {
        f"{s.planned.scored.candidate.symbol}:{s.planned.scored.candidate.strike}"
        for s in saved
    }
    assert keys == {"SOFI:18.0", "SOFI:19.0"}


def test_select_signals_dedupes_int_float_strike_keys():
    a = _signal("SOFI", 18, confidence=70)
    b = _signal("SOFI", 18.0, confidence=68)
    saved = select_signals_to_save([a, b], limit=10, max_per_symbol=5)
    assert len(saved) == 1


def test_select_signals_one_primary_per_symbol_expiry_same_side():
    """Two calls on the same expiry collapse to the higher-confidence strike."""
    weaker = _signal("SOFI", 18.0, confidence=60, profit_probability=52)
    stronger = _signal("SOFI", 19.5, confidence=72, profit_probability=61)
    saved = select_signals_to_save([weaker, stronger], limit=10, max_per_symbol=5)
    assert len(saved) == 1
    assert saved[0].planned.scored.candidate.strike == 19.5
    assert "hedge_strategy" not in (saved[0].planned.scored.scoring_snapshot or {})


def test_select_signals_picks_confident_direction_and_attaches_hedge():
    call = _signal(
        "SOFI",
        18.0,
        option_type="call",
        confidence=74,
        profit_probability=62,
        premium=0.55,
    )
    put = _signal(
        "SOFI",
        17.0,
        option_type="put",
        confidence=61,
        profit_probability=54,
        premium=0.40,
    )
    saved = select_signals_to_save([call, put], limit=10, max_per_symbol=5)
    assert len(saved) == 1
    primary = saved[0].planned.scored
    assert primary.candidate.option_type == "call"
    hedge = primary.scoring_snapshot.get("hedge_strategy")
    assert hedge is not None
    assert hedge["option_type"] == "put"
    assert hedge["strike"] == 17.0
    assert hedge["role"] == "opposite_side_hedge"
    assert hedge["confidence_score"] == 61.0
    assert hedge["profit_probability"] == 54.0


def test_select_signals_put_can_win_as_primary_with_call_hedge():
    call = _signal("AMD", 120.0, option_type="call", confidence=58, profit_probability=53)
    put = _signal("AMD", 115.0, option_type="put", confidence=71, profit_probability=60)
    saved = select_signals_to_save([call, put], limit=10, max_per_symbol=5)
    assert len(saved) == 1
    primary = saved[0].planned.scored
    assert primary.candidate.option_type == "put"
    hedge = primary.scoring_snapshot["hedge_strategy"]
    assert hedge["option_type"] == "call"
    assert hedge["strike"] == 120.0


def test_select_signals_skips_half_strike_twins_across_expiries():
    a = _signal("SOFI", 18.0, confidence=70, dte=14)
    twin = _signal("SOFI", 18.5, confidence=69, dte=14)
    b = _signal("SOFI", 19.5, confidence=68, dte=21)
    saved = select_signals_to_save([a, twin, b], limit=10, max_per_symbol=5)
    strikes = sorted(s.planned.scored.candidate.strike for s in saved)
    # Same-expiry twins collapse to one primary; later expiry still saves.
    assert strikes == [18.0, 19.5]


def test_select_signals_caps_per_symbol_then_backfills():
    # Different expirations so directional collapse does not wipe diversity.
    pool = [_signal("SOFI", 10.0 + i, dte=7 + i * 3, confidence=70 - i) for i in range(10)]
    pool += [_signal("NVDA", 100.0, confidence=80), _signal("AAPL", 200.0, confidence=78)]
    saved = select_signals_to_save(pool, limit=6, max_per_symbol=MAX_PER_SYMBOL)
    assert len(saved) == 6
    counts = {}
    for s in saved:
        sym = s.planned.scored.candidate.symbol
        counts[sym] = counts.get(sym, 0) + 1
    assert counts.get("NVDA") == 1
    assert counts.get("AAPL") == 1
    assert counts.get("SOFI", 0) >= MAX_PER_SYMBOL
    assert counts["SOFI"] + counts["NVDA"] + counts["AAPL"] == 6


def test_select_signals_prefers_symbol_spread_when_interleaved():
    pool = []
    for i in range(4):
        pool.append(_signal("SOFI", 10.0 + i, dte=7 + i * 3, confidence=70 - i))
        pool.append(_signal("NVDA", 100.0 + i, dte=7 + i * 3, confidence=69 - i))
        pool.append(_signal("AAPL", 200.0 + i, dte=7 + i * 3, confidence=68 - i))
    saved = select_signals_to_save(pool, limit=6, max_per_symbol=2)
    counts = {}
    for s in saved:
        sym = s.planned.scored.candidate.symbol
        counts[sym] = counts.get(sym, 0) + 1
    assert counts == {"SOFI": 2, "NVDA": 2, "AAPL": 2}


def test_select_signals_respects_overall_limit():
    pool = [_signal(f"T{i}", 10.0, confidence=60) for i in range(50)]
    saved = select_signals_to_save(pool, limit=MAX_SIGNALS_STORED, max_per_symbol=3)
    assert len(saved) == MAX_SIGNALS_STORED
    symbols = {s.planned.scored.candidate.symbol for s in saved}
    assert len(symbols) >= 10
