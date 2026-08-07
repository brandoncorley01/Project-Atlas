"""Tests for durable performance grading and formatting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.outcome_resolver import signal_from_performance_row
from app.services.performance_service import PerformanceService
from app.services.stock_options_grading import grade_options_pick, grade_stock_pick


def test_format_entry_includes_scoring_snapshot():
    row = {
        "id": "perf-1",
        "module": "options",
        "signal_id": "11111111-1111-1111-1111-111111111111",
        "outcome": "pending",
        "return_pct": None,
        "hold_duration_hours": None,
        "logged_at": "2026-08-01T00:00:00+00:00",
        "created_at": "2026-08-01T00:00:00+00:00",
        "resolution_source": "auto_scan",
        "signal_label": "AAPL call 200",
        "opportunity_score": 72,
        "confidence_score": 60,
        "scoring_snapshot": {
            "pick_origin": "atlas",
            "underlying": "AAPL",
            "option_type": "call",
            "strike": 200,
            "expiration": "2026-08-15",
            "premium": 2.5,
            "atlas_tracked": True,
        },
    }
    formatted = PerformanceService._format_entry(row)
    assert formatted["scoring_snapshot"]["underlying"] == "AAPL"
    assert formatted["scoring_snapshot"]["strike"] == 200
    assert formatted["pick_origin"] == "atlas"
    assert formatted["signal_label"] == "AAPL call 200"


def test_compute_summary_no_recursion():
    rows = [
        {
            "module": "sports",
            "outcome": "win",
            "return_pct": 110,
            "resolution_source": "auto_sports",
            "scoring_snapshot": {"pick_origin": "atlas"},
        },
        {
            "module": "options",
            "outcome": "loss",
            "return_pct": -40,
            "resolution_source": "manual",
            "scoring_snapshot": {"pick_origin": "user", "user_tracked": True},
        },
    ]
    svc = PerformanceService(db=None, user_id="u1")  # type: ignore[arg-type]
    summary = svc._compute_summary(rows, days=30, module=None)
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert "sports" in summary["by_module"]
    assert "options" in summary["by_module"]
    assert summary["by_module"]["sports"]["by_module"] == {}


def test_signal_from_performance_row_rebuilds_options():
    row = {
        "signal_id": "22222222-2222-2222-2222-222222222222",
        "logged_at": "2026-07-01T00:00:00+00:00",
        "scoring_snapshot": {
            "underlying": "NVDA",
            "option_type": "put",
            "strike": 120,
            "expiration": (datetime.now(UTC) - timedelta(days=1)).date().isoformat(),
            "premium": 3.0,
            "pick_origin": "atlas",
        },
    }
    sig = signal_from_performance_row(row)
    assert sig["id"] == row["signal_id"]
    assert sig["underlying"] == "NVDA"
    assert sig["strike"] == 120
    graded = grade_options_pick(sig, spot_price=100.0)
    assert graded is not None
    outcome, ret = graded
    assert outcome in {"win", "loss", "scratch"}
    assert isinstance(ret, float)


def test_signal_from_performance_row_rebuilds_stock():
    row = {
        "signal_id": "33333333-3333-3333-3333-333333333333",
        "logged_at": "2026-07-01T00:00:00+00:00",
        "scoring_snapshot": {
            "ticker": "MSFT",
            "recommendation": "buy",
            "entry_range": {"low": 400, "high": 410},
            "stop_loss": 390,
            "profit_targets": [430],
            "current_price": 405,
            "status": "expired",
        },
    }
    sig = signal_from_performance_row(row)
    graded = grade_stock_pick(sig, current_price=435.0)
    assert graded is not None
    assert graded[0] == "win"
    assert graded[1] > 0


def test_signal_from_performance_row_rebuilds_sports():
    row = {
        "signal_id": "44444444-4444-4444-4444-444444444444",
        "scoring_snapshot": {
            "sport": "NBA",
            "bet_type": "moneyline",
            "selection": "Lakers",
            "odds_american": -120,
            "event_name": "Lakers vs Celtics",
            "event_start": "2026-08-01T00:00:00+00:00",
            "sport_key": "basketball_nba",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "pick": {"bet_type": "moneyline", "team_or_side": "Lakers"},
        },
    }
    sig = signal_from_performance_row(row)
    assert sig["bet_type"] == "moneyline"
    assert sig["selection"] == "Lakers"
    assert sig["scoring_snapshot"]["sport_key"] == "basketball_nba"


def test_props_are_not_auto_gradeable_but_moneylines_are():
    from app.services.outcome_resolver import is_auto_gradeable_sports

    ml = {
        "bet_type": "moneyline",
        "selection": "Lakers",
        "scoring_snapshot": {"sport_key": "basketball_nba", "bet_type": "moneyline"},
    }
    prop = {
        "bet_type": "player_prop",
        "selection": "LeBron over 25.5 pts",
        "scoring_snapshot": {"sport_key": "basketball_nba", "is_player_prop": True},
    }
    assert is_auto_gradeable_sports(ml) is True
    assert is_auto_gradeable_sports(prop) is False


def test_match_completed_game_fuzzy_teams():
    from app.services.sports_grading import match_completed_game

    sig = {
        "event_name": "Boston Celtics vs Los Angeles Lakers",
        "scoring_snapshot": {
            "home_team": "Los Angeles Lakers",
            "away_team": "Boston Celtics",
            "sport_key": "basketball_nba",
        },
    }
    games = [
        {
            "id": "g1",
            "completed": True,
            "home_team": "Lakers",
            "away_team": "Celtics",
            "scores": [{"name": "Lakers", "score": "110"}, {"name": "Celtics", "score": "98"}],
        }
    ]
    assert match_completed_game(sig, games) is not None
