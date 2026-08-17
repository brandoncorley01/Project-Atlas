"""US FanDuel/DK market lines must still fill Today's MLB/WNBA slate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agents.sports_analyst import analyze_event
from app.services.sports_service import _select_diverse_setups


def _fd_dk_event(
    *,
    home: str,
    away: str,
    sport_key: str,
    sport_label: str,
    hours_from_now: float,
    home_ml: int = -120,
    away_ml: int = 100,
) -> dict:
    commence = (datetime.now(UTC) + timedelta(hours=hours_from_now)).isoformat().replace(
        "+00:00", "Z"
    )
    return {
        "id": f"{sport_key}-{home}-{away}",
        "home_team": home,
        "away_team": away,
        "commence_time": commence,
        "_sport_key": sport_key,
        "_sport_label": sport_label,
        "sport_title": sport_label,
        "bookmakers": [
            {
                "key": "fanduel",
                "title": "FanDuel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": home, "price": home_ml},
                            {"name": away, "price": away_ml},
                        ],
                    }
                ],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                # Identical prices → edge≈0 vs median (the production failure mode).
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": home, "price": home_ml},
                            {"name": away, "price": away_ml},
                        ],
                    }
                ],
            },
        ],
    }


def test_analyze_event_keeps_zero_edge_us_mlb_tonight():
    event = _fd_dk_event(
        home="Yankees",
        away="Red Sox",
        sport_key="baseball_mlb",
        sport_label="MLB",
        hours_from_now=3,
    )
    setups = analyze_event(event, calibration={"slate_mode": False})
    assert setups, "Tonight's MLB with agreeing FD/DK lines must still produce a pick"
    assert all(s.opportunity_score >= 24 for s in setups)
    assert any((s.scoring_snapshot or {}).get("us_market_line") for s in setups)


def test_analyze_event_keeps_zero_edge_wnba_in_slate_mode():
    event = _fd_dk_event(
        home="Liberty",
        away="Aces",
        sport_key="basketball_wnba",
        sport_label="WNBA",
        hours_from_now=5,
        home_ml=-110,
        away_ml=-110,
    )
    setups = analyze_event(event, calibration={"slate_mode": True, "sports_min_opportunity": 18})
    assert setups
    assert any("WNBA" in s.sport or s.sport == "WNBA" for s in setups)


def test_select_diverse_reserves_calendar_today():
    from app.services.sports_ranking import is_calendar_today

    rows = []
    # 20 strong tomorrow plays
    for i in range(20):
        start = (datetime.now(UTC) + timedelta(hours=30 + i)).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "id": f"tmr-{i}",
                "sport": "Soccer",
                "event_name": f"A{i} @ B{i}",
                "event_start": start,
                "bet_type": "moneyline",
                "selection": f"A{i}",
                "opportunity_score": 70 - i * 0.1,
                "confidence_score": 60,
                "risk_score": 40,
                "scoring_snapshot": {"sport_key": "soccer_epl", "event_id": f"e-tmr-{i}", "edge_pct": 3},
                "line_movement": {"edge_pct": 3, "event_id": f"e-tmr-{i}"},
            }
        )
    # 8 weaker tonight MLB plays
    for i in range(8):
        start = (datetime.now(UTC) + timedelta(hours=2 + i * 0.2)).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "id": f"mlb-{i}",
                "sport": "MLB",
                "event_name": f"Away{i} @ Home{i}",
                "event_start": start,
                "bet_type": "moneyline",
                "selection": f"Home{i}",
                "opportunity_score": 40 - i * 0.2,
                "confidence_score": 50,
                "risk_score": 45,
                "scoring_snapshot": {
                    "sport_key": "baseball_mlb",
                    "event_id": f"e-mlb-{i}",
                    "edge_pct": 0,
                    "us_market_line": True,
                },
                "line_movement": {"edge_pct": 0, "event_id": f"e-mlb-{i}"},
            }
        )

    picked = _select_diverse_setups(rows, limit=40)
    today_n = sum(1 for r in picked if is_calendar_today(r))
    assert today_n >= 8, f"expected all 8 calendar-today MLB picks reserved first, got {today_n} in {len(picked)} picks"
