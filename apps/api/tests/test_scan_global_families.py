"""Premium Scan must live-seed missing tennis and other global sport families."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.providers.sports import odds_api


def _cache_with_near_keys(*keys: str, empty: tuple[str, ...] = ()) -> dict:
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
    sports = {k: 3 for k in keys}
    for k in empty:
        sports[k] = 0
    return {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": events,
        "stats": {
            "sport_keys": list(keys)
            + list(empty)
            + [
                "tennis_atp_us_open",
                "tennis_wta_us_open",
                "tennis_atp_china_open",
                "tennis_wta_china_open",
                "soccer_epl",
                "golf_pga_championship",
            ],
            "sports": sports,
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
    assert any(k.startswith("tennis_") for k in missing)


def test_league_keys_missing_global_skips_dead_us_open():
    """After US Open ends, do not keep live-seeding keys that already returned 0 rows."""
    cache = _cache_with_near_keys(
        "baseball_mlb",
        "basketball_wnba",
        "soccer_usa_mls",
        empty=("tennis_atp_us_open", "tennis_wta_us_open"),
    )
    with (
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(
            odds_api,
            "_seasonal_global_candidates",
            return_value=("tennis_atp_china_open", "tennis_wta_china_open"),
        ),
    ):
        missing = odds_api.league_keys_missing_global_families()
    assert "tennis_atp_us_open" not in missing
    assert "tennis_wta_us_open" not in missing
    assert any(k.startswith("tennis_") for k in missing)


def test_us_open_not_essential_mid_september():
    mid_sep = datetime(2026, 9, 14, 18, 0, tzinfo=UTC)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return mid_sep
            return mid_sep.astimezone(tz)

    with patch("app.providers.sports.odds_api.datetime", _FixedDateTime):
        essentials = odds_api._essential_keys_for_today()
        seasonal = odds_api._seasonal_global_candidates("tennis")
    assert "tennis_atp_us_open" not in essentials
    assert "tennis_wta_us_open" not in essentials
    assert "tennis_atp_china_open" in seasonal


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


def test_slate_needs_live_seed_false_when_no_viable_global_left():
    """When dead Slam keys are known empty and no seasonal tennis remains, stop seeding."""
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
    cache = _cache_with_near_keys(
        "baseball_mlb",
        "basketball_wnba",
        "soccer_usa_mls",
        "soccer_epl",
        "mma_mixed_martial_arts",
        empty=(
            "tennis_atp_us_open",
            "tennis_wta_us_open",
            "tennis_atp_china_open",
            "tennis_wta_china_open",
            "tennis_atp_shanghai_masters",
            "tennis_wta_wuhan_open",
            "golf_pga_championship",
            "golf_the_open_championship",
            "golf_masters_tournament",
        ),
    )
    with (
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(odds_api, "_seasonal_global_candidates", return_value=()),
        patch.object(odds_api, "league_keys_missing_today_slate", return_value=()),
    ):
        assert odds_api.league_keys_missing_global_families() == ()
        assert odds_api.slate_needs_live_seed(status, scan) is False
