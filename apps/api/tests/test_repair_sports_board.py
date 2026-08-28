"""Repair sports board: warm-cache rescore first; live seed only when needed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sports_service import SportsRefreshService


@pytest.mark.asyncio
async def test_repair_cache_rescores_first_when_today_warm():
    """Warm Today cache must fill the board without spending Odds credits."""
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm = {
        "has_data": True,
        "cache_has_events": True,
        "missing_today_slate": False,
        "cache_needs_live_refresh": False,
        "today_event_count": 10,
        "near_term_event_count": 50,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value=warm,
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 12,
                    "today_picks_saved": 8,
                    "message": "cached rescore",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True,
        limit=40,
        force_refresh=False,
        cache_only=True,
        bypass_cooldown=True,
    )
    assert result["repair_mode"] == "cache_rescore"
    assert result["ok"] is True
    assert result["signals_created"] == 12


@pytest.mark.asyncio
async def test_repair_live_seeds_when_cache_rescore_saves_nothing():
    """Warm cache + empty board after free rescore → live Fetch, then rescore again."""
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm = {
        "has_data": True,
        "missing_today_slate": False,
        "today_event_count": 10,
        "near_term_event_count": 200,
    }
    live = AsyncMock(
        side_effect=[
            {"ok": False, "signals_created": 0, "signals_kept": False, "message": "no setups"},
            {"ok": False, "signals_created": 0, "signals_kept": False, "message": "save failed"},
            {
                "ok": True,
                "signals_created": 11,
                "today_picks_saved": 8,
                "message": "cached rescore",
            },
        ]
    )
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value=warm,
        ),
        patch.object(svc, "_repair_live_fetch_allowed", new=AsyncMock(return_value=True)),
        patch.object(svc, "refresh_sports", new=live),
    ):
        result = await svc.repair_sports_board(limit=40)

    assert live.await_count == 3
    assert live.await_args_list[0].kwargs["cache_only"] is True
    assert live.await_args_list[1].kwargs["force_refresh"] is True
    assert live.await_args_list[2].kwargs["cache_only"] is True
    assert result["repair_mode"] in {"live_seed_after_cache", "cache_rescore_after_live", "premium_live_seed"}
    assert result["ok"] is True
    assert result["signals_created"] == 11


@pytest.mark.asyncio
async def test_repair_cold_cache_live_seeds():
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm = {
        "has_data": True,
        "missing_today_slate": False,
        "today_event_count": 6,
        "near_term_event_count": 20,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            side_effect=[
                {
                    "has_data": False,
                    "cache_has_events": False,
                    "missing_today_slate": True,
                    "cache_needs_live_refresh": True,
                    "today_event_count": 0,
                    "near_term_event_count": 0,
                },
                warm,
                warm,
            ],
        ),
        patch.object(svc, "_repair_live_fetch_allowed", new=AsyncMock(return_value=True)),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 5,
                    "live_odds_pulled": True,
                    "today_picks_saved": 5,
                    "message": "live scan",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    assert refresh.await_count >= 1
    assert refresh.await_args_list[0].kwargs["force_refresh"] is True
    assert result["repair_mode"] == "live_seed"
    assert result["cache_was_cold"] is True
    assert result["ok"] is True
    assert "Durable odds cache seeded" in (result.get("message") or "")


@pytest.mark.asyncio
async def test_repair_keeps_ok_when_picks_saved_even_if_today_empty():
    """Regression: ok=false after saving picks made the Sports UI skip board reload."""
    svc = SportsRefreshService(MagicMock(), "user-1")
    empty_today = {
        "has_data": True,
        "missing_today_slate": True,
        "today_event_count": 0,
        "near_term_event_count": 40,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            side_effect=[
                {
                    "has_data": False,
                    "missing_today_slate": True,
                    "today_event_count": 0,
                    "near_term_event_count": 0,
                },
                empty_today,
                empty_today,
            ],
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 9,
                    "live_odds_pulled": True,
                    "today_picks_saved": 0,
                    "message": "saved picks",
                }
            ),
        ),
    ):
        result = await svc.repair_sports_board()

    assert result["ok"] is True
    assert result["signals_created"] == 9
    assert result.get("today_still_empty") is True
    assert "error" not in result or result.get("error") in (None, "")
    assert "stayed on Today" in (result.get("message") or "")
    assert "switch Window to Next 48h" not in (result.get("message") or "")


@pytest.mark.asyncio
async def test_repair_skips_live_fetch_when_credits_exhausted():
    """Warm cache + no credits → free rescore only (Repair must not look dead)."""
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm = {
        "has_data": True,
        "missing_today_slate": False,
        "today_event_count": 10,
        "near_term_event_count": 200,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value=warm,
        ),
        patch.object(svc, "_repair_live_fetch_allowed", new=AsyncMock(return_value=False)),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 8,
                    "today_picks_saved": 6,
                    "message": "cached rescore",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True,
        limit=40,
        force_refresh=False,
        cache_only=True,
        bypass_cooldown=True,
    )
    assert result["repair_mode"] == "cache_rescore"
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_repair_cold_cache_uses_cache_when_no_credits():
    svc = SportsRefreshService(MagicMock(), "user-1")
    warm = {
        "has_data": True,
        "missing_today_slate": False,
        "today_event_count": 6,
        "near_term_event_count": 20,
    }
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            side_effect=[
                {
                    "has_data": False,
                    "missing_today_slate": True,
                    "today_event_count": 0,
                    "near_term_event_count": 0,
                },
                warm,
                warm,
            ],
        ),
        patch.object(svc, "_repair_live_fetch_allowed", new=AsyncMock(return_value=False)),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 5,
                    "today_picks_saved": 5,
                    "message": "cache only",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True, limit=40, force_refresh=False, cache_only=True, bypass_cooldown=True
    )
    assert result["repair_mode"] == "cache_rescore_no_credits"
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_repair_fails_closed_when_still_empty():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value={
                "has_data": False,
                "missing_today_slate": True,
                "today_event_count": 0,
                "near_term_event_count": 0,
            },
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={"ok": True, "signals_created": 0, "message": "no games"}
            ),
        ),
    ):
        result = await svc.repair_sports_board()

    assert result["ok"] is False
    assert result["signals_created"] == 0
    assert "error" in result
