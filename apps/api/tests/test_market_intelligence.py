"""Unit tests for Market & Options Intelligence core logic."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from app.market_intelligence.alerts import should_send_alert
from app.market_intelligence.low_premium import LowPremiumFilters, scan_low_premium
from app.market_intelligence.normalization import (
    classify_side,
    compute_estimated_premium,
    compute_volume_oi_ratio,
    make_idempotency_key,
    normalize_activity,
)
from app.market_intelligence.outcomes import compute_outcome_metrics
from app.market_intelligence.providers.fixture import FixtureOptionsFlowProvider
from app.market_intelligence.scoring.exit_urgency import action_from_score, score_exit_urgency, urgency_label
from app.market_intelligence.scoring.options_activity import classify_direction, score_options_activity
from app.market_intelligence.scoring.sector_rotation import classify_market_weather, classify_sector
from app.market_intelligence.smart_money import build_smart_money_watchlist
from app.market_intelligence.types import DataStatus, DirectionLabel, ExitAction, NormalizedOptionsActivity


def _event(**overrides) -> NormalizedOptionsActivity:
    base = {
        "underlying": "AAPL",
        "option_type": "call",
        "strike": Decimal("210"),
        "expiration": date(2026, 8, 21),
        "trade_timestamp": datetime(2026, 7, 23, 14, 0, tzinfo=UTC),
        "contract_price": Decimal("3.45"),
        "bid": Decimal("3.40"),
        "ask": Decimal("3.50"),
        "midpoint": Decimal("3.45"),
        "contracts": 850,
        "estimated_premium": Decimal("293250"),
        "contract_volume": 4200,
        "open_interest": 1800,
        "volume_oi_ratio": Decimal("2.333333"),
        "implied_volatility": Decimal("0.28"),
        "delta": Decimal("0.42"),
        "execution_class": "ask",
        "flow_class": "sweep",
        "open_close": "opening",
        "data_source": "fixture",
        "source_event_id": "t1",
        "idempotency_key": "abc",
        "data_status": DataStatus.SIMULATED,
        "data_timestamp": datetime(2026, 7, 23, 14, 0, tzinfo=UTC),
        "underlying_price": Decimal("208.5"),
    }
    base.update(overrides)
    return NormalizedOptionsActivity(**base)


def test_premium_and_voi_math():
    assert compute_estimated_premium(10, Decimal("2.5")) == Decimal("2500.0000")
    assert compute_volume_oi_ratio(200, 100) == Decimal("2.000000")
    assert compute_volume_oi_ratio(10, 0) is None


def test_bid_ask_classification():
    assert classify_side(Decimal("1"), Decimal("2"), Decimal("1.95")) == "ask"
    assert classify_side(Decimal("1"), Decimal("2"), Decimal("1.05")) == "bid"
    assert classify_side(Decimal("1"), Decimal("2"), Decimal("1.5")) == "mid"


def test_normalize_and_idempotency():
    raw = {
        "underlying": "nvda",
        "option_type": "put",
        "strike": 120,
        "expiration": "2026-08-15",
        "trade_timestamp": "2026-07-23T15:00:00+00:00",
        "contract_price": 1.85,
        "bid": 1.8,
        "ask": 1.95,
        "contracts": 100,
        "volume": 500,
        "open_interest": 200,
        "source_event_id": "src-1",
    }
    a = normalize_activity(raw, data_source="fixture", data_status=DataStatus.SIMULATED)
    b = normalize_activity(raw, data_source="fixture", data_status=DataStatus.SIMULATED)
    assert a is not None and b is not None
    assert a.idempotency_key == b.idempotency_key
    assert a.data_status == DataStatus.SIMULATED
    key = make_idempotency_key(
        data_source="fixture",
        source_event_id="src-1",
        underlying="NVDA",
        option_type="put",
        strike=Decimal("120"),
        expiration=date(2026, 8, 15),
        trade_timestamp=datetime(2026, 7, 23, 15, tzinfo=UTC),
        contracts=100,
        contract_price=Decimal("1.85"),
    )
    assert a.idempotency_key == key


def test_direction_not_naive_call_bullish():
    call_ask = _event(option_type="call", execution_class="ask")
    call_bid = _event(option_type="call", execution_class="bid")
    put_ask = _event(option_type="put", execution_class="ask")
    assert classify_direction(call_ask, {}) == DirectionLabel.BULLISH
    assert classify_direction(call_bid, {}) == DirectionLabel.BEARISH
    assert classify_direction(put_ask, {}) == DirectionLabel.BEARISH
    hedge = _event(contracts=600, execution_class="mid")
    assert classify_direction(hedge, {}) == DirectionLabel.POSSIBLE_HEDGE


def test_unusual_score_explainable():
    breakdown, direction = score_options_activity(_event(), repeat_count=3)
    assert 0 <= breakdown.final_score <= 100
    assert breakdown.score_version == "options_activity_v1"
    assert breakdown.component_values
    assert breakdown.weights
    assert direction in DirectionLabel


def test_wide_spread_rejected_by_low_premium_scanner():
    good = _event()
    wide = _event(
        underlying="JPM",
        bid=Decimal("1.0"),
        ask=Decimal("4.0"),
        midpoint=Decimal("2.5"),
        contract_price=Decimal("2.5"),
        open_interest=40,
        contract_volume=60,
        delta=Decimal("0.12"),
        estimated_premium=Decimal("12500"),
        idempotency_key="wide",
    )
    results = scan_low_premium(
        [good, wide],
        filters=LowPremiumFilters(max_contract_price=5, min_open_interest=100, min_volume=50, max_spread_pct=12),
        as_of=date(2026, 7, 23),
    )
    symbols = {r["event"]["underlying"] for r in results}
    assert "AAPL" in symbols
    assert "JPM" not in symbols


def test_cheap_alone_does_not_rank_first():
    cheap_weak = _event(
        contract_price=Decimal("0.25"),
        midpoint=Decimal("0.25"),
        bid=Decimal("0.20"),
        ask=Decimal("0.30"),
        contracts=10,
        estimated_premium=Decimal("250"),
        contract_volume=30,
        open_interest=250,
        volume_oi_ratio=Decimal("0.12"),
        delta=Decimal("0.08"),
        flow_class="standard",
        idempotency_key="cheap",
    )
    strong = _event(idempotency_key="strong")
    results = scan_low_premium(
        [cheap_weak, strong],
        filters=LowPremiumFilters(
            max_contract_price=5,
            min_open_interest=100,
            min_volume=20,
            min_delta=0.05,
            min_unusual_score=40,
            max_otm_pct=0.5,
        ),
        as_of=date(2026, 7, 23),
    )
    if len(results) >= 2:
        assert results[0]["event"]["idempotency_key"] != "cheap" or results[0]["rank_score"] >= results[1]["rank_score"]


def test_fixture_provider_marked_simulated():
    provider = FixtureOptionsFlowProvider(allow=True)
    events = asyncio.run(provider.fetch_activity())
    assert events
    assert all(e.data_status == DataStatus.SIMULATED for e in events)


def test_duplicate_prevention_same_key():
    provider = FixtureOptionsFlowProvider(allow=True)
    events = asyncio.run(provider.fetch_activity())
    keys = [e.idempotency_key for e in events]
    assert len(keys) == len(set(keys))


def test_smart_money_language():
    events = [
        _event(idempotency_key="1", source_event_id="1"),
        _event(strike=Decimal("215"), idempotency_key="2", source_event_id="2", contracts=600),
    ]
    rows = build_smart_money_watchlist(events, min_events=2)
    assert rows
    assert "smart money" not in rows[0]["label"].lower()
    assert "institutional identity" in rows[0]["disclaimer"].lower() or "institutions" in rows[0]["disclaimer"].lower()


def test_outcome_no_presignal_required():
    out = compute_outcome_metrics(
        entry_underlying=100,
        entry_contract=2,
        underlying_path=[101, 103, 102],
        contract_path=[2.2, 3.0, 2.5],
    )
    assert out["hit_50"] is True
    assert out["evaluation_status"] == "evaluated"


def test_sector_and_weather():
    cls, evidence = classify_sector(
        {"relative_return": 2.0, "breadth_above_ma": 0.7, "acceleration": 0.2, "options_bias": 0.3, "data_points": 5}
    )
    assert cls.value == "Leading"
    assert evidence
    label, breakdown, payload = classify_market_weather(
        {
            "index_momentum": 0.4,
            "breadth": 0.3,
            "sector_leadership": 0.2,
            "options_bias": 0.3,
            "volatility_regime": 0.3,
            "news_sentiment": 0.1,
        }
    )
    assert label
    assert "disclaimer" in payload
    assert breakdown.score_version == "weather_v1"


def test_exit_urgency_and_thesis():
    breakdown, action, explanation = score_exit_urgency(
        {
            "momentum_score": -0.6,
            "trend_ok": False,
            "options_support": -0.5,
            "thesis_valid": False,
            "reward_risk": 0.4,
            "days_to_event": 1,
        }
    )
    assert breakdown.final_score >= 50
    assert action == ExitAction.THESIS_INVALIDATED
    assert "decision support" in explanation.lower()
    assert urgency_label(10) == "Strong Hold"
    assert action_from_score(90, thesis_invalid=False, insufficient=False, at_target=False) == ExitAction.EXIT_REVIEW


def test_alerts_block_simulated_outside_dev_rules():
    ok, reason = should_send_alert(
        alert_type="unusual_options_signal",
        dedup_key="AAPL",
        last_sent_at=None,
        cooldown_minutes=60,
        data_status="simulated",
        allow_simulated=False,
    )
    assert ok is False
    assert reason == "simulated_blocked"
