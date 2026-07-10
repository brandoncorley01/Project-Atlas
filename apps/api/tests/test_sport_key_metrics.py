"""Sport-specific key metric comparison for Atlas insight."""

from app.services.sport_key_metrics import build_key_metrics_comparison, sport_family


def test_wnba_family_and_ppg_labels():
    assert sport_family("basketball_wnba", "WNBA") == "basketball"
    cmp = build_key_metrics_comparison(
        sport_key="basketball_wnba",
        sport_label="WNBA",
        home={
            "name": "Los Angeles Sparks",
            "record": "2-1",
            "win_pct": 66.7,
            "avg_scored": 84.0,
            "avg_allowed": 78.0,
            "form": "WWL",
            "home_record": "2-0",
            "games_sampled": 3,
        },
        away={
            "name": "Chicago Sky",
            "record": "1-2",
            "win_pct": 33.3,
            "avg_scored": 76.0,
            "avg_allowed": 82.0,
            "form": "LLW",
            "away_record": "0-2",
            "games_sampled": 3,
        },
        selection="Los Angeles Sparks",
        bet_type="moneyline",
        pick_support=18,
    )
    assert cmp["sport_family"] == "basketball"
    assert cmp["metric_labels"]["scored"] == "PPG"
    labels = {r["label"] for r in cmp["rows"]}
    assert "PPG" in labels
    assert "Opp PPG" in labels
    assert "Net PPG" in labels
    assert "support Atlas" in cmp["analysis"]


def test_mlb_uses_run_labels():
    cmp = build_key_metrics_comparison(
        sport_key="baseball_mlb",
        sport_label="MLB",
        home={"name": "A", "avg_scored": 5.2, "avg_allowed": 4.1, "win_pct": 55, "record": "3-2", "games_sampled": 5},
        away={"name": "B", "avg_scored": 4.0, "avg_allowed": 4.8, "win_pct": 40, "record": "2-3", "games_sampled": 5},
        selection="A",
        bet_type="moneyline",
    )
    assert cmp["metric_labels"]["scored"] == "R/G"
    assert any(r["label"] == "R/G" for r in cmp["rows"])
