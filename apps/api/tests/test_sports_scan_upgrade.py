"""Sports scan v2 — cached form, line snapshots, secondary Tonight markets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.agents.sports_analyst import _book_disagreement_edge, analyze_event
from app.providers.sports import line_snapshot
from app.providers.sports.team_stats import build_stats_index_from_cache
from app.services.sports_service import (
    SportsRefreshService,
    _ensure_today_secondary_markets,
    setup_to_row,
)
from app.services.sports_ranking import is_today_slate


def _tonight(hours: float = 3.0) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _mlb_event(*, eid: str, hours: float = 3.0, spread: bool = True, total: bool = True) -> dict:
    markets = [
        {
            "key": "h2h",
            "outcomes": [
                {"name": "Yankees", "price": -120},
                {"name": "Red Sox", "price": 110},
            ],
        },
    ]
    if spread:
        markets.append(
            {
                "key": "spreads",
                "outcomes": [
                    {"name": "Yankees", "price": -110, "point": -1.5},
                    {"name": "Red Sox", "price": -110, "point": 1.5},
                ],
            }
        )
    if total:
        markets.append(
            {
                "key": "totals",
                "outcomes": [
                    {"name": "Over", "price": -110, "point": 8.5},
                    {"name": "Under", "price": -110, "point": 8.5},
                ],
            }
        )
    return {
        "id": eid,
        "commence_time": _tonight(hours),
        "_sport_key": "baseball_mlb",
        "_sport_label": "MLB",
        "home_team": "Yankees",
        "away_team": "Red Sox",
        "bookmakers": [
            {"key": "fanduel", "title": "FanDuel", "markets": markets},
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": markets,
            },
        ],
    }


def test_book_disagreement_edge_when_fd_dk_split():
    assert _book_disagreement_edge([-110, 105]) >= 1.0
    assert _book_disagreement_edge([-110, -108]) == 0.0


def test_line_snapshot_and_prior_attach():
    event = _mlb_event(eid="e1")
    snap = line_snapshot.build_line_snapshot([event])
    assert "e1" in snap
    prior = {"e1": {"h2h|Yankees": -130}}
    attached = line_snapshot.attach_prior_lines([dict(event)], prior)
    assert attached[0]["_prior_lines"]["h2h|Yankees"] == -130


def test_analyze_event_marks_steam_on_favorable_line_move():
    event = _mlb_event(eid="e1")
    # analyze_event keeps one ML side — test steam on the side that wins selection.
    event["_prior_lines"] = {"h2h|Red Sox": 100}
    cal = {"slate_mode": True, "sports_min_edge_pct": 0.0, "sports_min_opportunity": 16.0}
    setups = analyze_event(event, calibration=cal)
    assert len(setups) >= 1
    moved = setups[0]
    assert (moved.line_movement or {}).get("line_move_am", 0) >= 8
    assert moved.sharp_indicator == "steam"


def test_build_stats_index_from_cache_disk_only():
    games = [
        {
            "id": "g1",
            "completed": True,
            "home_team": "Yankees",
            "away_team": "Red Sox",
            "scores": [
                {"name": "Yankees", "score": "5"},
                {"name": "Red Sox", "score": "3"},
            ],
        }
    ]
    with patch(
        "app.providers.sports.team_stats._read_cache",
        return_value={"fetched_at": datetime.now(UTC).isoformat(), "by_sport": {"baseball_mlb": games}},
    ):
        index = build_stats_index_from_cache([_mlb_event(eid="e1")])
    assert "baseball_mlb" in index


def test_ensure_today_secondary_markets_adds_spread_on_busy_slate():
    from app.agents.sports_analyst import SportsBetSetup

    today_odds = [_mlb_event(eid=f"mlb-{i}", hours=2 + i * 0.1) for i in range(10)]
    ml_setup = SportsBetSetup(
        sport="MLB",
        event_name="Red Sox @ Yankees",
        event_start=_tonight(2),
        bet_type="moneyline",
        selection="Yankees",
        odds_american=-120,
        odds_decimal=1.83,
        expected_value=0.0,
        line_movement={"event_id": "mlb-0", "edge_pct": 0},
        sharp_indicator="market",
        confidence_score=50.0,
        risk_score=45.0,
        opportunity_score=30.0,
        recommendation="ML",
        explanation="x",
        bull_case="x",
        bear_case="x",
        invalidation="x",
        suggested_action="watch",
        scoring_snapshot={"event_id": "mlb-0", "sport_key": "baseball_mlb"},
    )
    existing = [setup_to_row("user-1", ml_setup)]
    out, added = _ensure_today_secondary_markets(
        existing,
        today_odds,
        user_id="user-1",
        stats_index={},
        calibration={},
        min_games=8,
    )
    assert added >= 1
    bet_types = {str(r.get("bet_type")) for r in out if is_today_slate(r)}
    assert "spread" in bet_types or "total" in bet_types


@pytest.mark.asyncio
async def test_cache_scan_uses_stats_from_disk():
    from app.providers.sports import odds_api

    events = [_mlb_event(eid=f"mlb-{i}", hours=2.5 + i * 0.05) for i in range(6)]
    cache = {"fetched_at": datetime.now(UTC).isoformat(), "events": events, "stats": {}}
    games = [
        {
            "id": "g1",
            "completed": True,
            "home_team": "Yankees",
            "away_team": "Red Sox",
            "scores": [
                {"name": "Yankees", "score": "4"},
                {"name": "Red Sox", "score": "2"},
            ],
        }
    ]

    db = MagicMock()
    db.insert = AsyncMock(
        side_effect=lambda table, rows: [{**r, "id": f"id-{i}"} for i, r in enumerate(rows)]
    )
    db.select = AsyncMock(return_value=[])
    db.delete = AsyncMock()
    db.update = AsyncMock()

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
        patch.object(odds_api, "_read_prior_line_snapshot", return_value={}),
        patch(
            "app.providers.sports.team_stats._read_cache",
            return_value={"fetched_at": datetime.now(UTC).isoformat(), "by_sport": {"baseball_mlb": games}},
        ),
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
    assert result.get("stats", {}).get("stats_from_cache") is True
    assert result.get("stats", {}).get("scan_version") == 2
