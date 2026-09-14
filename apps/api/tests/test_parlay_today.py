"""Today vs 24–48h parlay category assignment."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.agents.parlay_categories import compute_parlay_time_meta
from app.services.sports_ranking import is_calendar_today


ET = ZoneInfo("America/New_York")


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _two_starts_later_today() -> tuple[str, str]:
    now = datetime.now(ET)
    end = now.replace(hour=23, minute=45, second=0, microsecond=0)
    if end <= now + timedelta(minutes=20):
        pytest.skip("Too close to Eastern midnight for same-day fixture")
    first = now + timedelta(minutes=30)
    second = min(first + timedelta(hours=2), end)
    if first.date() != now.date() or second.date() != now.date():
        pytest.skip("Could not place both legs on today's Eastern date")
    return _iso(first), _iso(second)


def _iso_hours_from_now_et(hours: float) -> str:
    return _iso(datetime.now(ET) + timedelta(hours=hours))


def test_is_calendar_today_for_tonight_game():
    start = _two_starts_later_today()[0]
    row = {
        "event_start": start,
        "bet_type": "moneyline",
        "scoring_snapshot": {},
    }
    assert is_calendar_today(row) is True


def test_is_calendar_today_false_for_tomorrow():
    row = {
        "event_start": _iso_hours_from_now_et(30),
        "bet_type": "moneyline",
        "scoring_snapshot": {},
    }
    assert is_calendar_today(row) is False


def test_parlay_meta_tags_today_when_all_legs_same_day():
    start_a, start_b = _two_starts_later_today()
    legs = [
        {"sports_signal_id": "1", "event_start": start_a},
        {"sports_signal_id": "2", "event_start": start_b},
    ]
    signal_map = {
        "1": {"id": "1", "event_start": start_a},
        "2": {"id": "2", "event_start": start_b},
    }
    meta = compute_parlay_time_meta(legs, signal_map)
    assert "today" in meta["categories"]
    assert "next_48h" not in meta["categories"]


def test_parlay_meta_tags_next_48h_when_legs_span_days():
    start_a, _ = _two_starts_later_today()
    start_b = _iso_hours_from_now_et(30)
    legs = [
        {"sports_signal_id": "1", "event_start": start_a},
        {"sports_signal_id": "2", "event_start": start_b},
    ]
    signal_map = {
        "1": {"id": "1", "event_start": start_a},
        "2": {"id": "2", "event_start": start_b},
    }
    meta = compute_parlay_time_meta(legs, signal_map)
    assert "next_48h" in meta["categories"]
    assert "today" not in meta["categories"]


def _signal(
    *,
    sid: str,
    hours: float,
    sport: str,
    event: str,
    opp: float = 40.0,
    risk: float = 45.0,
) -> dict:
    return {
        "id": sid,
        "sport": sport,
        "event_name": event,
        "event_start": _iso_hours_from_now_et(hours),
        "bet_type": "moneyline",
        "selection": "Home",
        "odds_american": -110,
        "odds_decimal": 1.91,
        "opportunity_score": opp,
        "confidence_score": 55.0,
        "risk_score": risk,
        "expected_value": 1.5,
        "bull_case": "edge",
        "explanation": "test",
        "scoring_snapshot": {},
        "line_movement": {},
    }


def test_build_all_parlays_next_48h_survives_dense_today_slate():
    """Dense Tonight must not starve the 24–48h tab (top-16 Today-first bug)."""
    from app.agents.parlay_builder import build_all_parlays

    # 20 calendar-Today legs — formerly filled the entire combo pool.
    today_legs = [
        _signal(
            sid=f"t-{i}",
            hours=1.0 + i * 0.2,
            sport="MLB",
            event=f"Away{i} @ Home{i}",
            opp=50 - i * 0.1,
        )
        for i in range(20)
    ]
    # Enough non-Today ≤48h legs for conservative (2) through aggressive (4).
    sports = ["NFL", "NBA", "NHL", "MLS", "NCAAF", "WNBA"]
    tomorrow_legs = [
        _signal(
            sid=f"n-{i}",
            hours=26.0 + i,
            sport=sports[i % len(sports)],
            event=f"TmrAway{i} @ TmrHome{i}",
            opp=42.0,
            risk=48.0,
        )
        for i in range(6)
    ]

    built = build_all_parlays(today_legs + tomorrow_legs)
    cats = {str(p.get("time_category") or "") for p in built}
    next_48 = [p for p in built if p.get("time_category") == "next_48h"]
    assert "today" in cats
    assert "next_48h" in cats, f"expected next_48h parlays, got categories={cats} n={len(built)}"
    assert len(next_48) >= 1
    for parlay in next_48:
        starts = [leg.get("event_start") for leg in parlay.get("legs") or []]
        assert starts
        # At least one leg must not be calendar Today.
        from app.services.sports_ranking import is_calendar_today

        leg_rows = [{"event_start": s, "bet_type": "moneyline", "scoring_snapshot": {}} for s in starts]
        assert not all(is_calendar_today(r) for r in leg_rows)
