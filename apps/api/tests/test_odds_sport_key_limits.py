"""Live scan key selection must pin in-season essentials."""

from __future__ import annotations

from unittest.mock import patch

from app.providers.sports import odds_api


SUMMER_AVAILABLE = (
    "baseball_mlb",
    "basketball_wnba",
    "soccer_usa_mls",
    "mma_mixed_martial_arts",
    "americanfootball_nfl_preseason",
    "basketball_nba",
    "icehockey_nhl",
    "boxing_boxing",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "soccer_spain_la_liga",
    "tennis_atp_us_open",
)


def _weekend_live_cap(configured: int) -> int:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if datetime.now(ZoneInfo("America/New_York")).weekday() in (4, 5, 6) and configured >= 8:
        return min(12, max(configured, 10))
    return configured


def test_limit_sport_keys_pins_all_summer_essentials_under_cap():
    with (
        patch.object(odds_api.config.settings, "odds_max_sports_per_scan", 8),
        patch.object(odds_api, "_essential_keys_for_month", return_value=odds_api.ESSENTIAL_SUMMER_KEYS),
    ):
        picked = odds_api._limit_sport_keys(SUMMER_AVAILABLE, force_refresh=True)

    for key in odds_api.ESSENTIAL_SUMMER_KEYS:
        assert key in picked, f"missing essential {key} in {picked}"
    assert len(picked) <= _weekend_live_cap(8)


def test_limit_sport_keys_cap6_still_keeps_essentials_before_globals():
    """Even on a tight 6-league cap, essentials are pinned (not dropped for EPL slots)."""
    with (
        patch.object(odds_api.config.settings, "odds_max_sports_per_scan", 6),
        patch.object(odds_api, "_essential_keys_for_month", return_value=odds_api.ESSENTIAL_SUMMER_KEYS),
    ):
        picked = odds_api._limit_sport_keys(SUMMER_AVAILABLE, force_refresh=True)

    # 5 summer essentials must all fit before any non-essential filler.
    for key in odds_api.ESSENTIAL_SUMMER_KEYS:
        assert key in picked
    assert len(picked) == 6
    # Remaining slot can be US or global filler — but not at the expense of MMA.
    assert "mma_mixed_martial_arts" in picked


def test_cache_needs_live_refresh_majority_not_all():
    with patch.object(odds_api, "_essential_keys_for_month", return_value=odds_api.ESSENTIAL_SUMMER_KEYS):
        # Only MLB — below majority → needs live
        assert odds_api._cache_needs_live_refresh(frozenset({"baseball_mlb"})) is True
        # MLB + WNBA + MLS = 3 of 5 → majority OK even if MMA/preseason missing
        assert (
            odds_api._cache_needs_live_refresh(
                frozenset({"baseball_mlb", "basketball_wnba", "soccer_usa_mls", "soccer_epl"})
            )
            is False
        )


def test_odds_cache_status_keeps_needs_live_under_spend_lock():
    from datetime import UTC, datetime, timedelta
    from zoneinfo import ZoneInfo

    now_et = datetime.now(ZoneInfo("America/New_York"))
    kick = (now_et + timedelta(hours=1)).astimezone(UTC)
    commence = kick.isoformat().replace("+00:00", "Z")
    cache = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "1",
                "commence_time": commence,
                "_sport_key": "baseball_mlb",
                "_sport_label": "MLB",
                "sport_title": "MLB",
            }
        ],
        "stats": {},
    }
    with (
        patch.object(odds_api, "_read_cache", return_value=cache),
        patch.object(odds_api.config.settings, "odds_spend_mode", "cache_only"),
        patch.object(odds_api, "_essential_keys_for_month", return_value=odds_api.ESSENTIAL_SUMMER_KEYS),
        patch.object(odds_api, "_cache_age_minutes", return_value=10.0),
    ):
        status = odds_api.odds_cache_status()

    assert status["near_term_event_count"] >= 1
    assert status["cache_rescore_free"] is True
    assert status["cache_needs_live_refresh"] is True
    assert status["spend_locked"] is True
    assert status["missing_today_slate"] is False
    assert status["today_event_count"] >= 1
