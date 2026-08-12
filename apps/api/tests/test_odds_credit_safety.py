"""Credit safety: Scan must not auto-spend; Fetch has a cooldown."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.providers.sports import odds_api


def _cache_with_mlb(*, minutes_ago: float = 5.0) -> dict:
    from datetime import UTC, datetime, timedelta

    fetched = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    commence = (datetime.now(UTC) + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    return {
        "fetched_at": fetched,
        "events": [
            {
                "id": "g1",
                "commence_time": commence,
                "_sport_key": "baseball_mlb",
                "_sport_label": "MLB",
                "sport_title": "MLB",
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {
            "last_live_fetch_at": fetched,
            "credits_used": 8,
        },
    }


@pytest.mark.asyncio
async def test_scan_under_spend_lock_never_live_seeds_incomplete_cache():
    """Previously incomplete essentials forced Scan → force_refresh and burned credits."""
    cache = _cache_with_mlb()
    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(
            odds_api,
            "_cache_needs_live_refresh",
            return_value=True,  # incomplete essentials
        ),
        patch.object(odds_api, "_select_active_client", new=AsyncMock()) as select_client,
    ):
        events, stats = await odds_api.fetch_all_sports_odds(force_refresh=False, cache_only=False)

    assert events
    assert stats.get("credits_used") == 0
    assert stats.get("cached") is True
    select_client.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_cooldown_serves_cache_with_zero_credits():
    cache = _cache_with_mlb(minutes_ago=3)
    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api.config.settings, "odds_live_fetch_cooldown_minutes", 20),
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(odds_api, "_select_active_client", new=AsyncMock()) as select_client,
    ):
        events, stats = await odds_api.fetch_all_sports_odds(force_refresh=True)

    assert events
    assert stats.get("credits_used") == 0
    assert stats.get("fetch_cooldown") is True
    select_client.assert_not_called()


@pytest.mark.asyncio
async def test_rescore_cache_only_never_calls_client():
    cache = _cache_with_mlb()
    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(odds_api, "_select_active_client", new=AsyncMock()) as select_client,
    ):
        events, stats = await odds_api.fetch_all_sports_odds(force_refresh=False, cache_only=True)

    assert events
    assert stats.get("credits_used") == 0
    select_client.assert_not_called()
