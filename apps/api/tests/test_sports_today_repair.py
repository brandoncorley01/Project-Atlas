"""Today slate: Repair must live-seed when cache lacks Eastern-calendar-today games."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.providers.sports import odds_api
from app.services.sports_service import SportsRefreshService


def _tomorrow_only_cache(*, minutes_ago: float = 5.0) -> dict:
    fetched = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    commence = (datetime.now(UTC) + timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    return {
        "fetched_at": fetched,
        "events": [
            {
                "id": "tmr1",
                "commence_time": commence,
                "_sport_key": "soccer_epl",
                "_sport_label": "EPL",
                "sport_title": "EPL",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
            }
        ],
        "stats": {"last_live_fetch_at": fetched, "credits_used": 8},
    }


def _tonight_et(hours: float = 2.0) -> str:
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/New_York"))
    if now.hour >= 22:
        hours = min(hours, 0.75)
    return (now + timedelta(hours=hours)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _tonight_mlb_cache(*, minutes_ago: float = 5.0) -> dict:
    fetched = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    commence = _tonight_et(2.0)
    return {
        "fetched_at": fetched,
        "events": [
            {
                "id": "mlb1",
                "commence_time": commence,
                "_sport_key": "baseball_mlb",
                "_sport_label": "MLB",
                "sport_title": "MLB",
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {"last_live_fetch_at": fetched, "credits_used": 8},
    }


def test_cache_missing_today_when_only_tomorrow_games():
    assert odds_api.cache_missing_today_slate(_tomorrow_only_cache()["events"]) is True
    assert odds_api.cache_missing_today_slate(_tonight_mlb_cache()["events"]) is False


def test_today_slate_is_calendar_et_not_rolling_24h():
    """Today slate is sports-day (6am ET roll) — not every game in the next 24 hours."""
    tonight = _tonight_mlb_cache()["events"]
    tomorrow_only = _tomorrow_only_cache()["events"]
    assert len(odds_api.today_slate_events(tonight)) == 1
    assert len(odds_api.today_slate_events(tomorrow_only)) == 0
    rolling = [
        {
            "id": "roll1",
            "commence_time": (datetime.now(UTC) + timedelta(hours=20)).isoformat().replace("+00:00", "Z"),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
            "home_team": "A",
            "away_team": "B",
        }
    ]
    assert len(odds_api.next_24h_events(rolling)) == 1
    # Afternoon/evening tomorrow (20h out from evening) stays off Today sports-day.
    from app.services.sports_ranking import is_today_slate, sports_slate_date
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    # Explicit early-AM tip tomorrow must land on Today's sports-day slate.
    early_am = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).replace(
        hour=1, minute=10
    )
    early_row = {
        "id": "early",
        "event_start": early_am.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "bet_type": "moneyline",
        "scoring_snapshot": {},
    }
    if sports_slate_date() == sports_slate_date(early_am):
        assert is_today_slate(early_row) is True
    afternoon = early_am.replace(hour=15, minute=0)
    afternoon_row = {
        "id": "aft",
        "event_start": afternoon.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "bet_type": "moneyline",
        "scoring_snapshot": {},
    }
    assert is_today_slate(afternoon_row) is False


def test_early_am_nightcap_is_today_slate_event():
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    if now.hour < 6:
        pytest.skip("Already in early-AM sports-day window")
    early = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).replace(
        hour=1, minute=5
    )
    event = {
        "id": "nightcap",
        "commence_time": early.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "_sport_key": "baseball_mlb",
        "_sport_label": "MLB",
        "home_team": "Dodgers",
        "away_team": "Giants",
    }
    assert odds_api._event_is_calendar_today(event) is False
    assert odds_api._event_is_today_slate(event) is True
    assert len(odds_api.today_slate_events([event])) == 1


@pytest.mark.asyncio
async def test_fetch_cooldown_bypassed_when_today_missing():
    cache = _tomorrow_only_cache(minutes_ago=3)
    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api.config.settings, "odds_live_fetch_cooldown_minutes", 20),
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(
            odds_api,
            "_select_active_client",
            new=AsyncMock(return_value=(None, [], {"quota_exhausted": True, "remaining": 0})),
        ) as select_client,
    ):
        _events, stats = await odds_api.fetch_all_sports_odds(force_refresh=True)

    assert stats.get("fetch_cooldown") is not True
    select_client.assert_awaited()


@pytest.mark.asyncio
async def test_repair_live_seeds_when_today_missing_even_if_near_term_warm():
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm_today = {
        "has_data": True,
        "missing_today_slate": False,
        "today_event_count": 8,
        "near_term_event_count": 40,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            side_effect=[
                {
                    "has_data": True,
                    "cache_has_events": True,
                    "missing_today_slate": True,
                    "cache_needs_live_refresh": True,
                    "today_event_count": 0,
                },
                warm_today,
                warm_today,
            ],
        ),
        patch.object(svc, "_premium_live_fetch_allowed", new=AsyncMock(return_value=True)),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                side_effect=[
                    {
                        "ok": False,
                        "signals_created": 0,
                        "today_still_empty": True,
                        "today_picks_saved": 0,
                        "message": "no today picks",
                    },
                    {
                        "ok": True,
                        "signals_created": 0,
                        "stats": {"credits_used": 3, "sports_scanned": 3},
                        "message": "live seed",
                    },
                    {
                        "ok": True,
                        "signals_created": 12,
                        "live_odds_pulled": True,
                        "today_picks_saved": 8,
                        "message": "live scan",
                    },
                ]
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    assert refresh.await_count >= 1
    live_calls = [c for c in refresh.await_args_list if c.kwargs.get("force_refresh")]
    assert live_calls, "expected at least one live seed when Today missing"
    assert result["repair_mode"] in {"live_seed", "premium_live_seed", "live_seed_after_cache"}
    assert result["missing_today_before"] is True
    assert result["ok"] is True
