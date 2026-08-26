"""Today event coverage — Scan must not drop Tonight's games or wipe a richer board."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sports_service import (
    _ensure_today_event_coverage,
    _select_diverse_setups,
    SportsRefreshService,
)


def _tonight(hours: float = 3.0) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _row(*, eid: str, sport: str = "MLB", sport_key: str = "baseball_mlb", hours: float = 3.0, opp: float = 40.0):
    start = _tonight(hours)
    return {
        "id": f"row-{eid}",
        "sport": sport,
        "event_name": f"Away @ Home {eid}",
        "event_start": start,
        "bet_type": "moneyline",
        "selection": "Home",
        "opportunity_score": opp,
        "confidence_score": 50,
        "risk_score": 45,
        "scoring_snapshot": {
            "sport_key": sport_key,
            "event_id": eid,
            "edge_pct": 0,
            "us_market_line": True,
            "source": "odds_api",
        },
        "line_movement": {"edge_pct": 0, "event_id": eid, "source": "odds_api"},
    }


def test_select_diverse_keeps_one_card_per_today_event():
    rows = [_row(eid=f"mlb-{i}", hours=2 + i * 0.1, opp=45 - i) for i in range(15)]
    # Strong tomorrow noise that used to crowd Tonight out.
    for i in range(30):
        start = (datetime.now(UTC) + timedelta(hours=30 + i)).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "id": f"tmr-{i}",
                "sport": "Soccer",
                "event_name": f"A{i} @ B{i}",
                "event_start": start,
                "bet_type": "moneyline",
                "selection": f"A{i}",
                "opportunity_score": 80 - i * 0.1,
                "confidence_score": 60,
                "risk_score": 40,
                "scoring_snapshot": {"sport_key": "soccer_epl", "event_id": f"e-tmr-{i}", "edge_pct": 3},
                "line_movement": {"edge_pct": 3, "event_id": f"e-tmr-{i}"},
            }
        )

    picked = _select_diverse_setups(rows, limit=40)
    today_eids = {
        str((r.get("scoring_snapshot") or {}).get("event_id") or "")
        for r in picked
        if str((r.get("scoring_snapshot") or {}).get("sport_key") or "") == "baseball_mlb"
    }
    assert len(today_eids) >= 15, f"expected all 15 Tonight MLB events, got {len(today_eids)}"


def test_ensure_today_event_coverage_fills_missing_games():
    from app.agents.sports_analyst import SportsBetSetup

    existing = [_row(eid="kept-1")]
    today_odds = [
        {
            "id": "kept-1",
            "home_team": "Yankees",
            "away_team": "Red Sox",
            "commence_time": _tonight(3),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
        },
        {
            "id": "missing-2",
            "home_team": "Dodgers",
            "away_team": "Giants",
            "commence_time": _tonight(4),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
        },
    ]
    setup = SportsBetSetup(
        sport="MLB",
        event_name="Giants @ Dodgers",
        event_start=_tonight(4),
        bet_type="moneyline",
        selection="Dodgers",
        odds_american=-120,
        odds_decimal=1.83,
        expected_value=0.0,
        line_movement={},
        sharp_indicator=None,
        confidence_score=50.0,
        risk_score=40.0,
        opportunity_score=28.0,
        recommendation="ML",
        explanation="x",
        bull_case="x",
        bear_case="x",
        invalidation="x",
        suggested_action="watch",
        scoring_snapshot={"event_id": "missing-2", "sport_key": "baseball_mlb", "us_market_line": True},
    )
    with (
        patch("app.services.sports_service.analyze_event", return_value=[setup]),
        patch(
            "app.services.sports_service.setup_to_row",
            return_value=_row(eid="missing-2", hours=4),
        ),
        patch("app.services.sports_service.lookup_match_stats", return_value=None),
    ):
        out = _ensure_today_event_coverage(
            existing,
            today_odds,
            user_id="user-1",
            stats_index={},
            calibration={},
        )

    eids = {str((r.get("scoring_snapshot") or {}).get("event_id") or "") for r in out}
    assert "kept-1" in eids
    assert "missing-2" in eids


@pytest.mark.asyncio
async def test_thin_today_scan_preserves_prior_tonight_picks():
    """A thin Scan must not delete a richer Tonight board (event data loss)."""
    db = MagicMock()
    prior = [_row(eid=f"prior-{i}", hours=2 + i * 0.2) for i in range(12)]
    for i, row in enumerate(prior):
        row["id"] = f"old-{i}"
        row["user_id"] = "user-1"
        row["status"] = "active"

    new_setups = [_row(eid="new-only-1", hours=3, opp=55)]
    new_setups[0]["user_id"] = "user-1"
    new_setups[0]["status"] = "active"

    db.select = AsyncMock(
        side_effect=[
            [],  # existing check paths may call select
            prior,  # active rows before delete
        ]
    )
    db.insert = AsyncMock(return_value=[{**new_setups[0], "id": "saved-1"}])
    db.delete = AsyncMock()
    db.update = AsyncMock(return_value=[])

    svc = SportsRefreshService(db, "user-1")
    events = [
        {
            "id": "new-only-1",
            "commence_time": _tonight(3),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
            "home_team": "A",
            "away_team": "B",
        }
    ]
    fetch_stats = {
        "configured": True,
        "cached": True,
        "credits_used": 0,
        "events": 1,
        "today_events": 1,
        "today_event_count": 1,
    }

    setup = MagicMock()
    setup.opportunity_score = 55.0
    cal = MagicMock()
    cal.get_adjustments = AsyncMock(return_value={"sports_min_opportunity": 20})
    stale = MagicMock()
    stale.expire_concluded_sports = AsyncMock()

    with (
        patch(
            "app.services.sports_service.fetch_all_sports_odds",
            new=AsyncMock(return_value=(events, fetch_stats)),
        ),
        patch("app.services.sports_service.filter_upcoming_events", side_effect=lambda e: e),
        patch("app.services.sports_service.is_within_horizon", return_value=True),
        patch("app.services.sports_service.hours_until_event", return_value=3),
        patch("app.services.calibration_service.CalibrationService", return_value=cal),
        patch("app.services.sports_service.analyze_event", return_value=[setup]),
        patch("app.services.sports_service.setup_to_row", return_value=new_setups[0]),
        patch(
            "app.services.sports_service._select_diverse_setups",
            side_effect=lambda rows, limit: rows[:limit],
        ),
        patch(
            "app.services.sports_service._ensure_today_event_coverage",
            side_effect=lambda rows, *a, **k: rows,
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
        patch("app.providers.sports.odds_api.today_slate_events", return_value=events),
        patch(
            "app.services.outcome_resolver.OutcomeResolverService.resolve_pending",
            new=AsyncMock(return_value={"resolved": 0}),
        ),
    ):
        # First select in refresh may be for empty-board path; force the replace path select.
        db.select = AsyncMock(return_value=prior)
        result = await svc.refresh_sports(replace=True, cache_only=True, limit=40)

    assert result.get("ok") is not False
    assert fetch_stats.get("thin_today_guard") is True
    assert int(fetch_stats.get("today_picks_preserved") or 0) >= 6
    # Must not delete every prior Tonight row.
    deleted_ids: set[str] = set()
    for call in db.delete.await_args_list:
        filters = call.args[1] if len(call.args) > 1 else call.kwargs.get("filters") or {}
        raw = str(filters.get("id") or "")
        if raw.startswith("in.("):
            deleted_ids.update(raw[4:-1].split(","))
    assert len(deleted_ids) < len(prior)


def test_reinject_today_events_restores_dropped_tonight_cards():
    from app.services.sports_service import _reinject_today_events

    tonight = [
        _row(eid=f"mlb-{i}", hours=2 + i * 0.1, opp=40 - i) for i in range(12)
    ]
    # Diversity "selected" only 2 Tonight + many tomorrow
    selected = tonight[:2] + [
        {
            "id": f"tmr-{i}",
            "sport": "Soccer",
            "event_name": f"A{i} @ B{i}",
            "event_start": (datetime.now(UTC) + timedelta(hours=30 + i)).isoformat().replace("+00:00", "Z"),
            "bet_type": "moneyline",
            "selection": f"A{i}",
            "opportunity_score": 90 - i,
            "confidence_score": 60,
            "risk_score": 40,
            "scoring_snapshot": {"sport_key": "soccer_epl", "event_id": f"e-tmr-{i}", "edge_pct": 3},
            "line_movement": {"edge_pct": 3, "event_id": f"e-tmr-{i}"},
        }
        for i in range(20)
    ]
    out = _reinject_today_events(selected, tonight, limit=40)
    today_eids = {
        str((r.get("scoring_snapshot") or {}).get("event_id") or "")
        for r in out
        if str((r.get("scoring_snapshot") or {}).get("sport_key") or "") == "baseball_mlb"
    }
    assert len(today_eids) >= 12, f"expected all Tonight MLB events reinjected, got {len(today_eids)}"


def test_ensure_today_event_coverage_fallback_without_bookmakers():
    """Metadata-only Tonight games still get one Today card per event."""
    today_odds = [
        {
            "id": "meta-1",
            "home_team": "Yankees",
            "away_team": "Red Sox",
            "commence_time": _tonight(3),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
        },
    ]
    out = _ensure_today_event_coverage(
        [],
        today_odds,
        user_id="user-1",
        stats_index={},
        calibration={"slate_mode": True},
    )
    assert len(out) == 1
    snap = out[0].get("scoring_snapshot") or {}
    assert snap.get("event_id") == "meta-1"
    assert snap.get("slate_fallback") is True
    assert out[0].get("event_start") == today_odds[0]["commence_time"]


@pytest.mark.asyncio
async def test_refresh_sports_saves_today_when_cache_lacks_bookmakers():
    """Scan must not leave Today empty when cache has Tonight metadata only."""
    from unittest.mock import PropertyMock

    from app.providers.sports import odds_api

    def _meta_mlb(i: int) -> dict:
        return {
            "id": f"mlb-{i}",
            "commence_time": _tonight(2 + i * 0.1),
            "_sport_key": "baseball_mlb",
            "_sport_label": "MLB",
            "sport_title": "MLB",
            "home_team": f"Home{i}",
            "away_team": f"Away{i}",
        }

    events = [_meta_mlb(i) for i in range(6)]
    cache = {"fetched_at": datetime.now(UTC).isoformat(), "events": events, "stats": {}}

    db = MagicMock()
    db.insert = AsyncMock(
        side_effect=lambda table, rows: [{**r, "id": f"id-{i}"} for i, r in enumerate(rows)]
    )
    db.select = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=None)
    db.update = AsyncMock(return_value=None)

    svc = SportsRefreshService(db, "user-1")
    with (
        patch.object(
            type(odds_api.config.settings),
            "odds_api_keys",
            new_callable=PropertyMock,
            return_value=["k1"],
        ),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch("app.services.calibration_service.CalibrationService") as Cal,
        patch("app.services.sports_service.fetch_sports_news", new=AsyncMock(return_value=[])),
        patch(
            "app.services.kalshi_public_pulse.enrich_setup_snapshots_with_kalshi",
            new=AsyncMock(side_effect=lambda x: x),
        ),
        patch("app.config.reload_settings"),
    ):
        Cal.return_value.get_adjustments = AsyncMock(return_value={"sports_min_opportunity": 24})
        result = await svc.refresh_sports(replace=True, limit=40, cache_only=True)

    assert result.get("ok") is True
    assert int(result.get("today_picks_saved") or 0) >= 6
    saved = db.insert.call_args[0][1]
    from app.services.sports_ranking import is_today_slate

    assert sum(1 for r in saved if is_today_slate(r)) >= 6
