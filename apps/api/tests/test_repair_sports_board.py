"""Repair sports board: warm = cache-only; cold = one live seed; empty = fail closed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sports_service import SportsRefreshService


@pytest.mark.asyncio
async def test_repair_warm_cache_uses_cache_only():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value={"has_data": True, "cache_has_events": True},
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={"ok": True, "signals_created": 3, "message": "rescored"}
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True, limit=40, force_refresh=False, cache_only=True
    )
    assert result["repair_mode"] == "cache_rescan"
    assert result["cache_was_cold"] is False
    assert result["ok"] is True
    assert result["signals_created"] == 3


@pytest.mark.asyncio
async def test_repair_cold_cache_live_seeds():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value={"has_data": False, "cache_has_events": False},
        ),
        patch.object(
            svc,
            "refresh_sports",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "signals_created": 5,
                    "live_odds_pulled": True,
                    "message": "live scan",
                }
            ),
        ) as refresh,
    ):
        result = await svc.repair_sports_board(limit=40)

    refresh.assert_awaited_once_with(
        replace=True, limit=40, force_refresh=True, cache_only=False
    )
    assert result["repair_mode"] == "live_seed"
    assert result["cache_was_cold"] is True
    assert result["ok"] is True
    assert "Durable odds cache seeded" in (result.get("message") or "")


@pytest.mark.asyncio
async def test_repair_fails_closed_when_still_empty():
    svc = SportsRefreshService(MagicMock(), "user-1")
    with (
        patch(
            "app.providers.sports.odds_api.odds_cache_status",
            return_value={"has_data": False},
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
