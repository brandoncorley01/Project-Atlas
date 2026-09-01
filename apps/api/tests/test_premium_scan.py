"""Premium Scan: cache rescore then targeted live seed for missing Tonight slates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.sports import odds_api
from app.services.sports_service import SportsRefreshService


def _warm_status(*, today: int = 10, missing_today: bool = False) -> dict:
    return {
        "has_data": True,
        "missing_today_slate": missing_today,
        "cache_needs_live_refresh": False,
        "today_event_count": today,
        "near_term_event_count": 50,
    }


def test_slate_needs_live_seed_cold_cache():
    assert odds_api.slate_needs_live_seed({"has_data": False, "near_term_event_count": 0}) is True


def test_slate_needs_live_seed_missing_today():
    assert odds_api.slate_needs_live_seed(_warm_status(today=0, missing_today=True)) is True


def test_slate_needs_live_seed_warm_board_filled():
    status = _warm_status()
    scan = {"signals_created": 12, "today_picks_saved": 8, "today_still_empty": False}
    assert odds_api.slate_needs_live_seed(status, scan) is False


def test_slate_needs_live_seed_today_empty_despite_other_picks():
    """Next 24h picks must not block live seed when Today (ET) board is still empty."""
    status = _warm_status()
    scan = {
        "signals_created": 20,
        "today_picks_saved": 0,
        "today_still_empty": True,
    }
    assert odds_api.slate_needs_live_seed(status, scan) is True


def test_slate_needs_live_seed_warm_cache_empty_board():
    status = _warm_status()
    scan = {"signals_created": 0, "signals_kept": False, "today_picks_saved": 0}
    assert odds_api.slate_needs_live_seed(status, scan) is True


def test_league_keys_missing_today_partial_mlb_only():
    commence = (datetime.now(UTC) + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    events = [
        {
            "id": "mlb1",
            "commence_time": commence,
            "_sport_key": "baseball_mlb",
            "home_team": "A",
            "away_team": "B",
        }
    ]
    with patch.object(odds_api, "_read_cache", return_value={"events": events}):
        missing = odds_api.league_keys_missing_today_slate()
    assert "baseball_mlb" not in missing
    assert len(missing) >= 1


@pytest.mark.asyncio
async def test_premium_scan_cache_only_when_slate_complete():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value=_warm_status(),
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 15,
                    "today_picks_saved": 10,
                    "today_still_empty": False,
                }
            ),
        ) as refresh,
        patch.object(svc, "_premium_live_fetch_allowed", new=AsyncMock(return_value=True)),
    ):
        result = await svc.premium_scan_sports(limit=40)

    refresh.assert_awaited_once_with(
        replace=True,
        limit=40,
        force_refresh=False,
        cache_only=True,
        bypass_cooldown=True,
    )
    assert result["premium_phase"] == "cache_rescore"
    assert result.get("premium_live_seed") is not True


@pytest.mark.asyncio
async def test_premium_scan_live_seeds_missing_today():
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm_after = _warm_status(today=8)
    refresh = AsyncMock(
        side_effect=[
            {"ok": False, "signals_created": 0, "today_still_empty": True},
            {"ok": True, "signals_created": 0, "stats": {"credits_used": 3, "sports_scanned": 3}},
            {"ok": True, "signals_created": 12, "today_picks_saved": 8, "today_still_empty": False},
        ]
    )
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            side_effect=[
                _warm_status(today=0, missing_today=True),
                warm_after,
            ],
        ),
        patch.object(svc, "refresh_sports", new=refresh),
        patch.object(svc, "_premium_live_fetch_allowed", new=AsyncMock(return_value=True)),
        patch.object(
            odds_api,
            "league_keys_missing_today_slate",
            return_value=("baseball_mlb", "basketball_wnba"),
        ),
    ):
        result = await svc.premium_scan_sports(limit=40)

    assert refresh.await_count == 3
    assert refresh.await_args_list[1].kwargs["force_refresh"] is True
    assert refresh.await_args_list[1].kwargs["sport_keys"] == ("baseball_mlb", "basketball_wnba")
    assert result["premium_phase"] == "live_seed_rescore"
    assert result["premium_live_seed"] is True


@pytest.mark.asyncio
async def test_premium_scan_skips_live_when_credits_blocked():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value=_warm_status(today=0, missing_today=True),
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(return_value={"ok": False, "signals_created": 0, "today_still_empty": True}),
        ) as refresh,
        patch.object(svc, "_repair_live_fetch_allowed", new=AsyncMock(return_value=False)),
    ):
        result = await svc.premium_scan_sports(limit=40)

    refresh.assert_awaited_once()
    assert result["premium_live_skipped"] is True
    assert result["premium_needs_live"] is True
