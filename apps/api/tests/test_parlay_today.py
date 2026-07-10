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
