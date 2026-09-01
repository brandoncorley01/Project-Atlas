"""Premium Scan must live-seed missing tennis and other global sport families."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.providers.sports import odds_api


def _cache_with_near_keys(*keys: str) -> dict:
    commence = (datetime.now(UTC) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    events = [
        {
            "id": f"e-{k}",
            "commence_time": commence,
            "_sport_key": k,
            "_sport_label": k,
            "home_team": "A",
            "away_team": "B",
        }
        for k in keys
    ]
    return {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": events,
        "stats": {
            "sport_keys": list(keys)
            + [
                "tennis_atp_us_open",
                "tennis_wta_us_open",
                "soccer_epl",
                "golf_pga_championship",
            ],
        },
    }


def test_priority_scope_keeps_dynamic_tennis_tournament_keys():
    keys = (
        "baseball_mlb",
        "tennis_atp_cincinnati_open",
        "tennis_wta_cincinnati_open",
        "soccer_epl",
        "zz_unknown_league",
    )
    with patch.object(odds_api.config.settings, "odds_scan_scope", "priority"):
        limited = odds_api._limit_sport_keys(keys, force_refresh=False)
    assert "tennis_atp_cincinnati_open" in limited
    assert "tennis_wta_cincinnati_open" in limited
    assert "soccer_epl" in limited
    assert "zz_unknown_league" not in limited


def test_league_keys_missing_global_families_includes_tennis():
    cache = _cache_with_near_keys(
        "baseball_mlb",
        "basketball_wnba",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
    )
    with patch.object(odds_api, "_read_cache", return_value=cache):
        missing = odds_api.league_keys_missing_global_families()
    assert "tennis_atp_us_open" in missing or any(k.startswith("tennis_") for k in missing)


def test_league_keys_for_premium_seed_merges_today_and_global():
    cache = _cache_with_near_keys("baseball_mlb")
    with patch.object(odds_api, "_read_cache", return_value=cache):
        keys = odds_api.league_keys_for_premium_seed()
    assert any(k.startswith("tennis_") for k in keys)


def test_slate_needs_live_seed_when_tennis_missing_despite_mlb_picks():
    status = {
        "has_data": True,
        "near_term_event_count": 20,
        "today_event_count": 8,
        "missing_today_slate": False,
        "cache_needs_live_refresh": False,
    }
    scan = {
        "signals_created": 15,
        "today_picks_saved": 6,
        "today_still_empty": False,
    }
    cache = _cache_with_near_keys("baseball_mlb", "basketball_wnba", "soccer_usa_mls")
    with patch.object(odds_api, "_read_cache", return_value=cache):
        assert odds_api.slate_needs_live_seed(status, scan) is True
