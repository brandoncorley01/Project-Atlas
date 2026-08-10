"""Search bet recovery helpers — identity + rebuild from snapshots."""

from app.services.sports_user_bets_service import SportsUserBetsService


def test_identity_key_includes_selection():
    svc = SportsUserBetsService(db=None, user_id="u1")  # type: ignore[arg-type]
    a = {
        "event_name": "Away @ Home",
        "bet_type": "moneyline",
        "selection": "Away",
        "scoring_snapshot": {"event_id": "evt-9"},
        "line_movement": {},
    }
    b = {
        "event_name": "Away @ Home",
        "bet_type": "moneyline",
        "selection": "Home",
        "scoring_snapshot": {"event_id": "evt-9"},
        "line_movement": {},
    }
    assert svc._identity_key(a) != svc._identity_key(b)
    assert svc._identity_key(a) == "evt-9|moneyline|away"


def test_row_from_performance_snapshot_marks_user_entry():
    svc = SportsUserBetsService(db=None, user_id="u1")  # type: ignore[arg-type]
    snap = {
        "event_name": "Lakers @ Celtics",
        "selection": "Lakers",
        "odds_american": -110,
        "bet_type": "moneyline",
        "sport": "NBA",
        "event_start": "2099-12-01T00:00:00Z",
        "scoring_snapshot": {
            "source": "user_entry",
            "user_entry": True,
            "pick_origin": "user",
            "event_id": "nba-1",
        },
    }
    nested = snap["scoring_snapshot"]
    row = svc._row_from_performance_snapshot("sig-1", snap, nested)
    assert row is not None
    assert row["id"] == "sig-1"
    assert row["status"] == "active"
    assert row["opportunity_score"] >= 82
    assert row["scoring_snapshot"]["user_entry"] is True
    assert row["scoring_snapshot"]["recovered_from_performance"] is True
