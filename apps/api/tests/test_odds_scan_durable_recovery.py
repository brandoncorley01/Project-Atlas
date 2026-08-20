"""Cold Scan must recover from durable cache instead of failing closed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from app.providers.sports import odds_api


@pytest.mark.asyncio
async def test_cache_only_scan_recovers_from_durable_when_disk_cold(tmp_path):
    soon = (datetime.now(UTC) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    remote = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "mlb1",
                "_sport_key": "baseball_mlb",
                "_sport_label": "MLB",
                "commence_time": soon,
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {},
    }
    cache_path = tmp_path / ".odds_cache.json"
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api, "_read_cache", return_value=None),
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=remote),
    ):
        events, stats = await odds_api.fetch_all_sports_odds(cache_only=True)

    assert stats.get("error") is None
    assert stats.get("cached") is True
    assert len(events) >= 1
    assert events[0]["id"] == "mlb1"
    assert cache_path.exists()
