"""Focused Earnings Intelligence tests — deterministic fixtures only."""

from __future__ import annotations

from app.market_intelligence.earnings.engine import evaluate_earnings_setup
from app.market_intelligence.earnings.ev import (
    expected_value,
    liquidity_ok,
    micro_coattail_size,
    otm_passes_gates,
    reachable_breakeven,
)
from app.market_intelligence.earnings.expected_move import (
    blend_expected_move,
    estimate_iv_crush_pct,
    expected_move_from_iv,
    expected_move_from_straddle,
    historical_avg_move,
)
from app.market_intelligence.earnings.fixture_data import FIXTURE_CHAINS, FIXTURE_EVENTS
from app.market_intelligence.earnings.types import EarningsRecType, EarningsStrategy


def test_expected_move_and_ev_math():
    hist = historical_avg_move([6.2, 9.1, 5.4, 11.0])
    assert hist == 7.93 or abs(hist - 7.925) < 0.02
    iv_move = expected_move_from_iv(price=210, iv=0.32, days_to_event=1)
    assert iv_move is not None and iv_move > 0
    straddle = expected_move_from_straddle(price=210, call_mid=7.8, put_mid=7.6)
    assert straddle is not None and abs(straddle - ((7.8 + 7.6) / 210) * 100) < 0.01
    blended = blend_expected_move(straddle_pct=straddle, iv_pct=iv_move, historical_pct=hist)
    assert blended["expected_move_pct"] is not None
    crush = estimate_iv_crush_pct(pre_iv=0.32, historical_crush=31)
    assert crush == 31.0
    ev = expected_value(probability_of_profit=0.5, avg_gain=20, avg_loss=10, estimated_costs=2)
    assert ev == 0.5 * 20 - 0.5 * 10 - 2


def test_weak_otm_rejected():
    event = next(e for e in FIXTURE_EVENTS if e.symbol == "WEAK")
    chain = FIXTURE_CHAINS["WEAK"]
    rec = evaluate_earnings_setup(event, chain, normal_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation in (
        EarningsRecType.AVOID,
        EarningsRecType.WATCH,
        EarningsRecType.INSUFFICIENT_DATA,
    )
    assert rec.recommendation != EarningsRecType.QUALIFIED_TRADE
    c = chain["contracts"][0]
    ok, reasons = liquidity_ok(volume=c.volume, open_interest=c.open_interest, spread=c.spread_pct)
    assert ok is False
    assert reasons


def test_valid_otm_can_qualify_or_micro():
    event = next(e for e in FIXTURE_EVENTS if e.symbol == "AAPL")
    chain = FIXTURE_CHAINS["AAPL"]
    rec = evaluate_earnings_setup(event, chain, normal_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation in (
        EarningsRecType.MICRO_COATTAIL,
        EarningsRecType.QUALIFIED_TRADE,
        EarningsRecType.WATCH,
    )
    assert not hasattr(rec, "paper_only") or getattr(rec, "paper_only", None) is None
    assert rec.expected_move_pct is not None
    assert rec.estimated_iv_crush_pct is not None
    c = next(x for x in chain["contracts"] if x.moneyness == "otm")
    ok, _ = liquidity_ok(volume=c.volume, open_interest=c.open_interest, spread=c.spread_pct)
    assert ok is True
    reach_ok, _ = reachable_breakeven(
        breakeven_pct=((c.strike + c.premium) / event.price - 1) * 100,
        expected_move_pct=rec.expected_move_pct,
        historical_avg_pct=rec.historical_avg_move_pct,
    )
    assert reach_ok is True or rec.strategy == EarningsStrategy.DEBIT_SPREAD


def test_micro_coattail_sizing_respects_limits():
    size = micro_coattail_size(
        normal_risk_usd=100,
        fraction=0.18,
        max_loss_per_contract=18,
    )
    assert "paper_only" not in size
    assert size["position_size_usd"] == 18.0
    assert size["fraction"] == 0.18


def test_missing_stale_cannot_produce_qualified_trade():
    event = next(e for e in FIXTURE_EVENTS if e.symbol == "STALE")
    rec = evaluate_earnings_setup(event, None, normal_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation == EarningsRecType.INSUFFICIENT_DATA
    assert rec.strategy == EarningsStrategy.NO_TRADE
    assert rec.position_size_usd == 0


def test_desk_payload_has_real_data_shape():
    from app.market_intelligence.earnings.service_api import _pack_desk

    desk = _pack_desk(
        FIXTURE_EVENTS,
        FIXTURE_CHAINS,
        normal_risk_usd=100,
        micro_fraction=0.18,
        meta={"provider": "test", "data_status": "delayed", "symbol_count": len(FIXTURE_EVENTS)},
    )
    assert "paper_only" not in desk
    assert "normal_risk_usd" in desk["config"]
    assert desk["config"]["micro_max_risk_usd"] == 18.0
    for rec in desk["recently_reviewed"]:
        assert "paper_only" not in rec
        assert "position_size_usd" in rec
    gates = {
        "liquidity_ok": False,
        "breakeven_reachable": True,
        "positive_ev": True,
        "max_loss_defined": True,
        "within_risk_limit": True,
    }
    passes, fails = otm_passes_gates(gates)
    assert passes is False
    assert any("liquidity" in f for f in fails)


def test_liquidity_ok_accepts_yahoo_zero_oi_with_volume():
    ok, reasons = liquidity_ok(volume=1200, open_interest=0, spread=4.0)
    assert ok is True, reasons
    ok_low, reasons_low = liquidity_ok(volume=40, open_interest=0, spread=4.0)
    assert ok_low is False
    assert reasons_low


def test_options_candidates_accept_zero_oi_high_volume(monkeypatch):
    """Regression: Yahoo currently returns openInterest=0 on liquid names."""
    from datetime import date, timedelta

    import pandas as pd

    from app.engine.models import CandidateOpportunity, SignalModule
    from app.providers.options import yahoo as yahoo_mod

    class _FakeTicker:
        @property
        def options(self):
            exp = (date.today() + timedelta(days=10)).isoformat()
            return [exp]

        def option_chain(self, _exp):
            frame = pd.DataFrame(
                [
                    {
                        "strike": 210.0,
                        "bid": 0.0,
                        "ask": 0.0,
                        "lastPrice": 3.45,
                        "volume": 4200,
                        "openInterest": 0,
                        "impliedVolatility": 0.32,
                    }
                ]
            )

            class Chain:
                calls = frame
                puts = frame.copy()

            return Chain()

    class _FakeYf:
        @staticmethod
        def Ticker(_symbol):
            return _FakeTicker()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf())

    cands = yahoo_mod.fetch_options_candidates("AAPL", {"price": 208.0})
    assert cands, "expected candidates when OI=0 but volume is strong"
    assert all(isinstance(c, CandidateOpportunity) for c in cands)
    assert cands[0].module == SignalModule.OPTIONS
    assert cands[0].open_interest == 0
    assert cands[0].volume >= 50


def test_otm_passes_gates_all_green():
    ok, fails = otm_passes_gates(
        {
            "liquidity_ok": True,
            "breakeven_reachable": True,
            "positive_ev": True,
            "max_loss_defined": True,
            "within_risk_limit": True,
        }
    )
    assert ok is True
    assert fails == []
