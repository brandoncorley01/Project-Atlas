"""Sports scan persistence — insert before delete, surface save failures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.sports_service import SportsRefreshService


def _setup_row(i: int = 0) -> dict:
    return {
        "id": f"new-{i}",
        "user_id": "user-1",
        "sport": "MLB",
        "selection": f"Team {i}",
        "opportunity_score": 55.0 + i,
        "scoring_snapshot": {"source": "odds_api"},
        "line_movement": {},
    }


def _patch_scan(events, fetch_stats, setup_row):
    setup = MagicMock()
    setup.opportunity_score = 60.0

    cal = MagicMock()
    cal.get_adjustments = AsyncMock(return_value={"sports_min_opportunity": 20})

    stale = MagicMock()
    stale.expire_concluded_sports = AsyncMock()

    return (
        patch(
            "app.services.sports_service.fetch_all_sports_odds",
            new=AsyncMock(return_value=(events, fetch_stats)),
        ),
        patch("app.services.sports_service.filter_upcoming_events", side_effect=lambda e: e),
        patch("app.services.sports_service.is_within_horizon", return_value=True),
        patch("app.services.sports_service.hours_until_event", return_value=12),
        patch("app.services.calibration_service.CalibrationService", return_value=cal),
        patch("app.services.sports_service.analyze_event", return_value=[setup]),
        patch("app.services.sports_service.setup_to_row", return_value=setup_row),
        patch(
            "app.services.sports_service._select_diverse_setups",
            side_effect=lambda rows, limit: rows[:limit],
        ),
        patch("app.services.sports_service.tag_pool_categories"),
        patch("app.services.sports_service.fetch_sports_news", new=AsyncMock(return_value=[])),
        patch("app.services.sports_service.sort_for_display", side_effect=lambda rows: rows),
        patch("app.services.sports_service.is_sports_actionable", return_value=True),
        patch("app.services.sports_service.lookup_match_stats", return_value=None),
        patch("app.config.reload_settings"),
        patch("app.services.stale_signal_service.StaleSignalService", return_value=stale),
        patch(
            "app.services.kalshi_public_pulse.enrich_setup_snapshots_with_kalshi",
            new=AsyncMock(side_effect=lambda rows: rows),
        ),
    )


@pytest.mark.asyncio
async def test_refresh_sports_recovers_when_insert_returns_empty_representation():
    """PostgREST [] after write must not leave Repair/Scan on an empty board."""
    db = MagicMock()
    recovered = {
        **_setup_row(0),
        "id": "db-1",
        "selection": "Yankees",
        "bet_type": "moneyline",
        "scoring_snapshot": {"source": "odds_api", "event_id": "e1"},
        "line_movement": {},
    }
    setup_row = {
        **_setup_row(0),
        "selection": "Yankees",
        "bet_type": "moneyline",
        "scoring_snapshot": {"source": "odds_api", "event_id": "e1"},
        "line_movement": {},
    }
    db.select = AsyncMock(return_value=[recovered])
    db.insert = AsyncMock(return_value=[])
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [{"id": "e1", "commence_time": "2099-01-01T00:00:00Z", "sport_title": "MLB"}]
    fetch_stats = {"configured": True, "cached": True, "credits_used": 0, "events": 1}

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patch_scan(events, fetch_stats, setup_row):
            stack.enter_context(p)
        result = await svc.refresh_sports(replace=True, cache_only=True)

    assert result.get("ok") is True
    assert result["signals_created"] == 1
    assert result["stats"].get("insert_empty_representation") is True
    db.insert.assert_awaited()
    # Only the recovered row is active — nothing older to delete.
    assert result.get("ok") is True


@pytest.mark.asyncio
async def test_refresh_sports_keeps_board_when_insert_fails():
    db = MagicMock()
    db.select = AsyncMock(return_value=[{"id": "old-1", "status": "active"}])
    db.insert = AsyncMock(side_effect=HTTPException(status_code=502, detail="Database error"))
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [{"id": "e1", "commence_time": "2099-01-01T00:00:00Z", "sport_title": "MLB"}]
    fetch_stats = {"configured": True, "cached": True, "credits_used": 0, "events": 1}

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patch_scan(events, fetch_stats, _setup_row(0)):
            stack.enter_context(p)
        result = await svc.refresh_sports(replace=True, cache_only=True)

    assert result.get("ok") is True
    assert result["signals_created"] == 0
    assert result.get("signals_kept") is True
    assert "unchanged" in (result.get("message") or "").lower()
    db.delete.assert_not_called()
    db.insert.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_sports_save_failure_empty_board_not_marked_kept():
    db = MagicMock()
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock(return_value=[])
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [{"id": "e1", "commence_time": "2099-01-01T00:00:00Z", "sport_title": "MLB"}]
    fetch_stats = {"configured": True, "cached": True, "credits_used": 0, "events": 1}

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patch_scan(events, fetch_stats, _setup_row(0)):
            stack.enter_context(p)
        result = await svc.refresh_sports(replace=True, cache_only=True)

    assert result.get("ok") is False
    assert result["signals_created"] == 0
    assert result.get("signals_kept") is False
    assert "could not save" in (result.get("message") or "").lower()


@pytest.mark.asyncio
async def test_refresh_sports_deletes_old_odds_rows_only_after_successful_insert():
    db = MagicMock()
    old_row = {
        "id": "old-1",
        "scoring_snapshot": {"source": "odds_api"},
        "line_movement": {},
    }
    db.select = AsyncMock(
        return_value=[
            old_row,
            {"id": "new-0", "scoring_snapshot": {"source": "odds_api"}, "line_movement": {}},
        ]
    )
    db.insert = AsyncMock(return_value=[_setup_row(0)])
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [{"id": "e1", "commence_time": "2099-01-01T00:00:00Z", "sport_title": "MLB"}]
    fetch_stats = {"configured": True, "cached": True, "credits_used": 0, "events": 1}

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patch_scan(events, fetch_stats, _setup_row(0)):
            stack.enter_context(p)
        result = await svc.refresh_sports(replace=True, cache_only=True)

    assert result.get("ok") is True
    assert result["signals_created"] == 1
    db.insert.assert_awaited()
    db.delete.assert_awaited()
    delete_filter = db.delete.await_args.args[1]
    assert "old-1" in delete_filter["id"]
    assert "new-0" not in delete_filter["id"]


@pytest.mark.asyncio
async def test_refresh_sports_fails_closed_when_empty_board_and_no_setups():
    db = MagicMock()
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock()
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [{"id": "e1", "commence_time": "2099-01-01T00:00:00Z", "sport_title": "MLB"}]
    fetch_stats = {"configured": True, "cached": True, "credits_used": 0, "events": 1}

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patch_scan(events, fetch_stats, _setup_row(0)):
            stack.enter_context(p)
        stack.enter_context(patch("app.services.sports_service.analyze_event", return_value=[]))
        stack.enter_context(
            patch("app.services.sports_service._select_diverse_setups", return_value=[])
        )
        result = await svc.refresh_sports(replace=True, cache_only=True)

    assert result.get("ok") is False
    assert result["signals_created"] == 0
    assert result.get("signals_kept") is False
    db.insert.assert_not_called()


def test_live_odds_pulled_requires_events_and_credits():
    assert SportsRefreshService._live_odds_pulled(
        cache_only=False,
        fetch_stats={"configured": True, "cached": False, "credits_used": 4, "events": 12},
    )
    assert not SportsRefreshService._live_odds_pulled(
        cache_only=False,
        fetch_stats={"configured": True, "cached": False, "credits_used": 4, "events": 0},
    )
    assert not SportsRefreshService._live_odds_pulled(
        cache_only=False,
        fetch_stats={"configured": True, "cached": True, "credits_used": 0, "events": 12},
    )
    assert not SportsRefreshService._live_odds_pulled(
        cache_only=True,
        fetch_stats={"configured": True, "cached": False, "credits_used": 4, "events": 12},
    )
    assert not SportsRefreshService._live_odds_pulled(
        cache_only=False,
        fetch_stats={
            "configured": True,
            "cached": False,
            "credits_used": 4,
            "events": 0,
            "error": "Live odds pull returned no upcoming games",
        },
    )
