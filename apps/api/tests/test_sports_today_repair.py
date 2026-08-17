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


def _tonight_mlb_cache(*, minutes_ago: float = 5.0) -> dict:
    fetched = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    commence = (datetime.now(UTC) + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
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
                {
                    "has_data": True,
                    "missing_today_slate": False,
                    "today_event_count": 8,
                },
            ],
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 12,
                    "live_odds_pulled": True,
                    "message": "live scan",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True, limit=40, force_refresh=True, cache_only=False, bypass_cooldown=True
    )
    assert result["repair_mode"] == "live_seed"
    assert result["missing_today_before"] is True
    assert result["ok"] is True
