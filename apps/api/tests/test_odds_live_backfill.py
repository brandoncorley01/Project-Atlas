"""Live Fetch backfills empty league slots so Tonight is not starved."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from app.providers.sports import odds_api


@pytest.mark.asyncio
async def test_live_fetch_backfills_empty_essential_slots():
    """Ended preseason / empty MMA must not consume the whole 8-league Tonight budget."""
    from datetime import UTC, datetime, timedelta

    soon = (datetime.now(UTC) + timedelta(hours=6)).isoformat().replace("+00:00", "Z")

    async def fake_fetch(client, key, title, sem, *, outright=False):
        if key == "americanfootball_nfl_preseason":
            return key, []
        if key == "mma_mixed_martial_arts":
            return key, []
        if key == "soccer_epl":
            return key, [
                {
                    "id": "epl1",
                    "commence_time": soon,
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "_sport_key": key,
                    "_sport_label": "EPL",
                }
            ]
        if key == "tennis_atp_us_open":
            return key, [
                {
                    "id": "atp1",
                    "commence_time": soon,
                    "home_team": "Player A",
                    "away_team": "Player B",
                    "_sport_key": key,
                    "_sport_label": "ATP US Open",
                }
            ]
        return key, [
            {
                "id": f"{key}-1",
                "commence_time": soon,
                "home_team": "Home",
                "away_team": "Away",
                "_sport_key": key,
                "_sport_label": key,
            }
        ]

    client = AsyncMock()
    client.requests_remaining = 100
    client.requests_used = 10
    client.quota_exhausted = False

    all_sports = [
        {"key": k, "title": k, "active": True}
        for k in (
            "baseball_mlb",
            "basketball_wnba",
            "soccer_usa_mls",
            "mma_mixed_martial_arts",
            "americanfootball_nfl_preseason",
            "soccer_epl",
            "tennis_atp_us_open",
            "boxing_boxing",
            "soccer_spain_la_liga",
        )
    ]

    with (
        patch.object(type(odds_api.config.settings), "odds_api_keys", new_callable=PropertyMock, return_value=["k1"]),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api.config.settings, "odds_max_sports_per_scan", 5),
        patch.object(odds_api, "_essential_keys_for_month", return_value=odds_api.ESSENTIAL_SUMMER_KEYS),
        patch.object(odds_api, "_read_cache", return_value=None),
        patch.object(odds_api, "_write_cache"),
        patch.object(
            odds_api,
            "_select_active_client",
            new=AsyncMock(return_value=(client, all_sports, {"total_remaining": 200, "active_key_remaining": 200})),
        ),
        patch.object(odds_api, "_fetch_sport_odds", side_effect=fake_fetch),
        patch.object(odds_api, "invalidate_key_probe_cache"),
    ):
        events, stats = await odds_api.fetch_all_sports_odds(force_refresh=True)

    assert stats.get("live_backfill_keys"), f"expected backfill keys, got {stats}"
    sport_keys = set(stats.get("sport_keys") or [])
    assert "soccer_epl" in sport_keys or "tennis_atp_us_open" in sport_keys
    assert any(e.get("id") in {"epl1", "atp1"} for e in events)
