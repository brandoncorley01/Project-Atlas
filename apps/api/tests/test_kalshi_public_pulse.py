"""Kalshi public-probability matching + pulse builders."""

from __future__ import annotations

from app.providers.sports.kalshi import (
    _abbr,
    build_pulse_from_match,
    match_event,
    series_for_sport,
)


def test_series_for_sport_maps_majors():
    assert series_for_sport(sport_key="baseball_mlb") == "KXMLBGAME"
    assert series_for_sport(sport_key="americanfootball_nfl") == "KXNFLGAME"
    assert series_for_sport(sport="NHL") == "KXNHLGAME"
    assert series_for_sport(sport_key="golf_pga") is None


def test_match_event_orients_away_home():
    events = [
        {
            "event_ticker": "KXMLBGAME-26AUG08TORPHI",
            "title": "Toronto vs Philadelphia",
            "markets": [
                {
                    "ticker": "KXMLBGAME-26AUG08TORPHI-TOR",
                    "yes_sub_title": "Toronto",
                    "last_price_dollars": "0.3900",
                },
                {
                    "ticker": "KXMLBGAME-26AUG08TORPHI-PHI",
                    "yes_sub_title": "Philadelphia",
                    "last_price_dollars": "0.6200",
                },
            ],
        }
    ]
    matched = match_event(
        events,
        home_team="Philadelphia Phillies",
        away_team="Toronto Blue Jays",
    )
    assert matched is not None
    assert matched["market_a"]["yes_sub_title"] == "Toronto"
    assert matched["market_b"]["yes_sub_title"] == "Philadelphia"


def test_build_pulse_normalizes_and_stances():
    match = {
        "event": {"event_ticker": "KXNFLGAME-1", "title": "Tampa Bay vs Seattle"},
        "market_a": {
            "ticker": "A-SEA",
            "yes_sub_title": "Seattle",
            "last_price_dollars": "0.5400",
        },
        "market_b": {
            "ticker": "A-TB",
            "yes_sub_title": "Tampa Bay",
            "last_price_dollars": "0.4800",
        },
    }
    pulse = build_pulse_from_match(
        match,
        series_ticker="KXNFLGAME",
        selection="Seattle Seahawks",
        history_a=[51, 53, 54],
        history_b=[],
    )
    assert pulse["source"] == "kalshi"
    assert pulse["side_a"]["abbr"]
    assert pulse["side_a"]["implied_pct"] + pulse["side_b"]["implied_pct"] == 100.0
    assert len(pulse["history_a"]) >= 3
    assert len(pulse["history_b"]) == len(pulse["history_a"])
    assert pulse["history_a"][-1] == pulse["side_a"]["implied_pct"]
    assert pulse["stance_vs_pick"] in {"sure", "mixed", "doubtful"}


def test_abbr_shortens_names():
    assert _abbr("Seattle") == "SEA" or len(_abbr("Seattle")) <= 4
    assert _abbr("TB") == "TB"
