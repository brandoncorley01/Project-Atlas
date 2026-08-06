"""Options persistence selection — contract dedupe + per-symbol diversity."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.options_service import MAX_PER_SYMBOL, MAX_SIGNALS_STORED, select_signals_to_save


def _signal(symbol: str, strike: float, *, option_type: str = "call", dte: int = 14):
    candidate = SimpleNamespace(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiration=date.today() + timedelta(days=dte),
    )
    scored = SimpleNamespace(candidate=candidate)
    planned = SimpleNamespace(scored=scored)
    return SimpleNamespace(planned=planned)


def test_select_signals_dedupes_identical_contracts():
    a = _signal("SOFI", 18.0)
    dup = _signal("SOFI", 18.0)
    b = _signal("SOFI", 19.0)
    saved = select_signals_to_save([a, dup, b], limit=10, max_per_symbol=5)
    keys = {
        f"{s.planned.scored.candidate.symbol}:{s.planned.scored.candidate.strike}"
        for s in saved
    }
    assert keys == {"SOFI:18.0", "SOFI:19.0"}


def test_select_signals_caps_per_symbol_then_backfills():
    # Ranked board dumps many SOFI first — diversity pass should still pull NVDA/AAPL.
    pool = [_signal("SOFI", 10.0 + i) for i in range(10)]
    pool += [_signal("NVDA", 100.0), _signal("AAPL", 200.0)]
    saved = select_signals_to_save(pool, limit=6, max_per_symbol=MAX_PER_SYMBOL)
    assert len(saved) == 6
    counts = {}
    for s in saved:
        sym = s.planned.scored.candidate.symbol
        counts[sym] = counts.get(sym, 0) + 1
    assert counts.get("NVDA") == 1
    assert counts.get("AAPL") == 1
    # First pass keeps ≤ MAX_PER_SYMBOL SOFI; backfill may add more to fill limit.
    assert counts.get("SOFI", 0) >= MAX_PER_SYMBOL
    assert counts["SOFI"] + counts["NVDA"] + counts["AAPL"] == 6


def test_select_signals_prefers_symbol_spread_when_interleaved():
    pool = []
    for i in range(4):
        pool.append(_signal("SOFI", 10.0 + i))
        pool.append(_signal("NVDA", 100.0 + i))
        pool.append(_signal("AAPL", 200.0 + i))
    saved = select_signals_to_save(pool, limit=6, max_per_symbol=2)
    counts = {}
    for s in saved:
        sym = s.planned.scored.candidate.symbol
        counts[sym] = counts.get(sym, 0) + 1
    assert counts == {"SOFI": 2, "NVDA": 2, "AAPL": 2}

def test_select_signals_respects_overall_limit():
    pool = [_signal(f"T{i}", 10.0) for i in range(50)]
    saved = select_signals_to_save(pool, limit=MAX_SIGNALS_STORED, max_per_symbol=3)
    assert len(saved) == MAX_SIGNALS_STORED
    symbols = {s.planned.scored.candidate.symbol for s in saved}
    assert len(symbols) >= 10
