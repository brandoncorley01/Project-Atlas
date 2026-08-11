"""Cold live-seed credit accounting and empty-pull hard fail."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.providers.sports import odds_api


@pytest.mark.asyncio
async def test_live_pull_with_zero_events_returns_error_and_zero_credits():
    client = MagicMock()
    client.requests_remaining = 40
    client.requests_used = 6
    client.quota_exhausted = False

    async def _empty_fetch(client_arg, key, title, sem, outright=False):
        return key, []

    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api, "_read_cache", return_value=None),
        patch.object(
            odds_api,
            "_select_active_client",
            new=AsyncMock(
                return_value=(
                    client,
                    [{"key": "baseball_mlb", "title": "MLB", "active": True}],
                    {
                        "key_count": 1,
                        "active_key_index": 0,
                        "total_remaining": 40,
                        "active_key_remaining": 40,
                        "quota_exhausted": False,
                        "keys": [],
                    },
                )
            ),
        ),
        patch.object(odds_api, "_limit_sport_keys", return_value=("baseball_mlb",)),
        patch.object(odds_api, "_fetch_sport_odds", side_effect=_empty_fetch),
        patch.object(odds_api, "invalidate_key_probe_cache"),
        patch.object(odds_api, "_write_cache") as write_cache,
    ):
        events, stats = await odds_api.fetch_all_sports_odds(force_refresh=True)

    assert events == []
    assert stats.get("error")
    assert stats.get("credits_used") == 0
    write_cache.assert_not_called()


@pytest.mark.asyncio
async def test_probe_prefers_key_with_most_remaining_credits():
    low = MagicMock()
    high = MagicMock()

    async def _probe(i, _key):
        if i == 0:
            return {
                "valid": True,
                "exhausted": False,
                "remaining": 3,
                "_client": low,
                "_sports": [{"key": "baseball_mlb", "active": True}],
            }
        return {
            "valid": True,
            "exhausted": False,
            "remaining": 120,
            "_client": high,
            "_sports": [{"key": "baseball_mlb", "active": True}],
        }

    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["a", "b"]),
        patch.object(odds_api, "_probe_single_key", side_effect=_probe),
        patch.dict(odds_api._PROBE_CACHE, {"at": 0.0, "data": None}, clear=False),
    ):
        result = await odds_api.probe_all_odds_keys(use_cache=False)

    assert result["active_key_index"] == 1
    assert result["active_client"] is high
    assert result["active_key_remaining"] == 120
    assert result["total_remaining"] == 123
