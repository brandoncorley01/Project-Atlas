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
from app.market_intelligence.earnings.service_api import build_earnings_desk
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
    rec = evaluate_earnings_setup(event, chain, normal_paper_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation in (
        EarningsRecType.AVOID,
        EarningsRecType.WATCH,
        EarningsRecType.INSUFFICIENT_DATA,
    )
    assert rec.recommendation != EarningsRecType.QUALIFIED_TRADE
    # Liquidity gate must fail on the weak contract
    c = chain["contracts"][0]
    ok, reasons = liquidity_ok(volume=c.volume, open_interest=c.open_interest, spread=c.spread_pct)
    assert ok is False
    assert reasons


def test_valid_otm_can_qualify_or_micro():
    event = next(e for e in FIXTURE_EVENTS if e.symbol == "AAPL")
    chain = FIXTURE_CHAINS["AAPL"]
    rec = evaluate_earnings_setup(event, chain, normal_paper_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation in (
        EarningsRecType.MICRO_COATTAIL,
        EarningsRecType.QUALIFIED_TRADE,
        EarningsRecType.WATCH,
    )
    assert rec.paper_only is True
    assert rec.expected_move_pct is not None
    assert rec.estimated_iv_crush_pct is not None
    # OTM on AAPL should pass liquidity
    c = next(x for x in chain["contracts"] if x.moneyness == "otm")
    ok, _ = liquidity_ok(volume=c.volume, open_interest=c.open_interest, spread=c.spread_pct)
    assert ok is True
    reach_ok, _ = reachable_breakeven(
        breakeven_pct= ((c.strike + c.premium) / event.price - 1) * 100,
        expected_move_pct=rec.expected_move_pct,
        historical_avg_pct=rec.historical_avg_move_pct,
    )
    assert reach_ok is True or rec.strategy == EarningsStrategy.DEBIT_SPREAD


def test_micro_coattail_sizing_respects_limits():
    size = micro_coattail_size(
        normal_paper_risk_usd=100,
        fraction=0.18,
        max_loss_per_contract=18,
    )
    assert size["paper_only"] is True
    assert size["live_trading_enabled"] is False
    assert size["paper_position_size_usd"] == 18.0
    assert size["fraction"] == 0.18


def test_missing_stale_cannot_produce_qualified_trade():
    event = next(e for e in FIXTURE_EVENTS if e.symbol == "STALE")
    rec = evaluate_earnings_setup(event, None, normal_paper_risk_usd=100, micro_fraction=0.18)
    assert rec.recommendation == EarningsRecType.INSUFFICIENT_DATA
    assert rec.strategy == EarningsStrategy.NO_TRADE
    assert rec.paper_position_size_usd == 0


def test_feature_remains_paper_only():
    desk = build_earnings_desk(normal_paper_risk_usd=100, micro_fraction=0.18)
    assert desk["paper_only"] is True
    assert desk["live_trading_enabled"] is False
    assert desk["audit"]["live_trading_enabled"] is False
    for rec in desk["recently_reviewed"]:
        assert rec["paper_only"] is True
    # Large theoretical return cannot override failed gates
    gates = {
        "liquidity_ok": False,
        "breakeven_reachable": True,
        "positive_ev": True,
        "max_loss_defined": True,
        "within_risk_limit": True,
    }
    passes, fails = otm_passes_gates(gates)
    assert passes is False
    assert "liquidity" in fails


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
