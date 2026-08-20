"""The Odds API — odds across all active game sports (soccer, tennis, US leagues, etc.)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic as _monotonic
from typing import Any

import httpx

from app import config
from app.services.freshness import filter_upcoming_events, hours_until_event

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
PARALLEL_FETCHES = 10
# 90 days — keep longer-dated game lines for better early odds; futures use a wider gate.
MAX_CACHE_HORIZON_HOURS = 2160
MAX_FUTURES_PER_MARKET = 8
MAX_FUTURES_SPORTS_PER_SCAN = 20

# Cache the last successful odds pull so repeated scans don't burn API credits,
# and so an exhausted quota degrades to last-known odds instead of nothing.
_CACHE_PATH = Path(__file__).resolve().parents[3] / ".odds_cache.json"

# Legacy fallback when API key missing or /sports fails.
DEFAULT_SPORT_KEYS = (
    "americanfootball_nfl",
    "americanfootball_nfl_preseason",
    "basketball_nba",
    "basketball_wnba",
    "baseball_mlb",
    "icehockey_nhl",
    "soccer_usa_mls",
    "soccer_epl",
    "soccer_fifa_world_cup",
    "mma_mixed_martial_arts",
    "boxing_boxing",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
)

# Prefer fetching these first. US majors lead; international is secondary fill.
PRIORITY_SPORT_KEYS = (
    "americanfootball_nfl",
    "americanfootball_nfl_preseason",
    "americanfootball_ncaaf",
    "baseball_mlb",
    "baseball_mlb_preseason",
    "basketball_nba",
    "basketball_wnba",
    "basketball_ncaab",
    "basketball_wncaab",
    "icehockey_nhl",
    "soccer_usa_mls",
    "mma_mixed_martial_arts",
    "boxing_boxing",
    "americanfootball_cfl",
    "soccer_epl",
    "soccer_fifa_world_cup",
    "soccer_uefa_champs_league",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_europa_league",
    "soccer_mexico_ligamx",
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "golf_pga_championship",
    "golf_the_open_championship",
)

ESSENTIAL_SUMMER_KEYS = frozenset(
    {
        "baseball_mlb",
        "basketball_wnba",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
        "americanfootball_nfl_preseason",
    }
)
ESSENTIAL_WINTER_KEYS = frozenset(
    {"basketball_nba", "icehockey_nhl", "americanfootball_nfl", "americanfootball_ncaaf"}
)

# Live Fetch prefers these US-book leagues first (FanDuel/DraftKings boards).
# International priority keys fill remaining slots — see _limit_sport_keys.
# Cap via ODDS_MAX_SPORTS_PER_SCAN.
CORE_US_LIVE_KEYS = (
    "baseball_mlb",
    "basketball_wnba",
    "basketball_nba",
    "basketball_ncaab",
    "americanfootball_nfl",
    "americanfootball_nfl_preseason",
    "americanfootball_ncaaf",
    "icehockey_nhl",
    "soccer_usa_mls",
    "mma_mixed_martial_arts",
    "boxing_boxing",
)

# Top global leagues mixed into every capped scan (FanDuel/DK still carry lines).
CORE_GLOBAL_LIVE_KEYS = (
    "soccer_epl",
    "soccer_uefa_champs_league",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_europa_league",
    "soccer_mexico_ligamx",
    "soccer_fifa_world_cup",
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "golf_pga_championship",
    "golf_the_open_championship",
)

# Only pull lines from American retail books — same credit cost, playable numbers.
US_BOOKMAKER_KEYS = "fanduel,draftkings"

# Sport families whose Odds API keys rotate (combat). Do NOT include soccer/tennis —
# those prefixes pin every foreign league and crowd out MLB/WNBA/NFL on the board.
PRIORITY_SPORT_PREFIXES = frozenset({"mma", "boxing"})

# Exact keys treated as the American FanDuel/DK board for ranking / diversification.
US_MARKET_SPORT_KEYS = frozenset(
    {
        "americanfootball_nfl",
        "americanfootball_nfl_preseason",
        "americanfootball_ncaaf",
        "americanfootball_cfl",
        "baseball_mlb",
        "baseball_mlb_preseason",
        "basketball_nba",
        "basketball_wnba",
        "basketball_ncaab",
        "basketball_wncaab",
        "icehockey_nhl",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
        "boxing_boxing",
    }
)
US_MARKET_SPORT_PREFIXES = (
    "americanfootball_",
    "baseball_mlb",
    "basketball_nba",
    "basketball_wnba",
    "basketball_ncaab",
    "basketball_wncaab",
    "icehockey_nhl",
    "soccer_usa_",
    "mma_",
    "boxing_",
)


def is_us_market_sport_key(sport_key: str | None) -> bool:
    key = str(sport_key or "").lower()
    if not key:
        return False
    if key in US_MARKET_SPORT_KEYS:
        return True
    return any(key.startswith(p) or key == p.rstrip("_") for p in US_MARKET_SPORT_PREFIXES)


SUMMER_PRIORITY_KEYS = (
    "baseball_mlb",
    "basketball_wnba",
    "soccer_usa_mls",
    "mma_mixed_martial_arts",
    "boxing_boxing",
    "americanfootball_nfl_preseason",
    "americanfootball_ncaaf",
    "americanfootball_cfl",
    "basketball_nba",
    "icehockey_nhl",
    "soccer_epl",
    "soccer_fifa_world_cup",
    "soccer_uefa_champs_league",
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "golf_pga_championship",
    "basketball_ncaab",
    "basketball_wncaab",
)

WINTER_PRIORITY_KEYS = (
    "basketball_nba",
    "icehockey_nhl",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_ncaab",
    "basketball_wncaab",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_usa_mls",
    "mma_mixed_martial_arts",
    "boxing_boxing",
    "tennis_atp_australian_open",
    "tennis_wta_australian_open",
    "baseball_mlb",
)

# Soft-deprioritize (scan last) — never hard-drop. Odds API `active` + near-term
# events decide whether a league has plays; calendar months only affect order.
OFF_SEASON_DEPRIORITIZE_BY_MONTH: dict[tuple[int, ...], frozenset[str]] = {
    (3, 4, 5, 6, 7): frozenset({"americanfootball_nfl"}),
    (7, 8, 9): frozenset({"basketball_nba"}),
    (6, 7, 8): frozenset({"icehockey_nhl"}),
}

# Back-compat alias used by cache refresh heuristics.
OFF_SEASON_SKIP_BY_MONTH = OFF_SEASON_DEPRIORITIZE_BY_MONTH

IN_SEASON_RETRY_KEYS = frozenset(
    {
        "baseball_mlb",
        "basketball_wnba",
        "basketball_nba",
        "icehockey_nhl",
        "americanfootball_nfl",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
    }
)

SPORT_LABELS = {
    "americanfootball_nfl": "NFL",
    "americanfootball_nfl_preseason": "NFL Preseason",
    "americanfootball_ncaaf": "NCAAF",
    "americanfootball_cfl": "CFL",
    "basketball_nba": "NBA",
    "basketball_wnba": "WNBA",
    "basketball_ncaab": "NCAAB",
    "basketball_wncaab": "NCAAW",
    "baseball_mlb": "MLB",
    "baseball_mlb_preseason": "MLB Preseason",
    "icehockey_nhl": "NHL",
    "soccer_usa_mls": "MLS",
    "soccer_fifa_world_cup": "FIFA World Cup",
    "soccer_epl": "EPL",
    "soccer_spain_la_liga": "La Liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "UCL",
    "soccer_uefa_europa_league": "UEL",
    "soccer_mexico_ligamx": "Liga MX",
    "soccer_brazil_campeonato": "Brasileirão",
    "mma_mixed_martial_arts": "MMA",
    "boxing_boxing": "Boxing",
    "golf_pga_championship": "PGA",
    "golf_the_open_championship": "The Open",
    "cricket_international_t20": "T20 Cricket",
    "rugbyleague_nrl": "NRL",
    "aussierules_afl": "AFL",
}


# Major championship / season futures — scanned when Odds API marks them active.
MAJOR_FUTURES_KEYS = (
    "americanfootball_nfl_super_bowl_winner",
    "basketball_nba_championship_winner",
    "basketball_wnba_championship_winner",
    "baseball_mlb_world_series_winner",
    "icehockey_nhl_championship_winner",
    "americanfootball_ncaaf_championship_winner",
    "basketball_ncaab_championship_winner",
    "soccer_fifa_world_cup_winner",
    "soccer_epl_winner",
    "soccer_uefa_champs_league_winner",
    "golf_masters_tournament_winner",
    "golf_pga_championship_winner",
    "golf_the_open_championship_winner",
    "golf_us_open_winner",
)


def _is_outright_sport(sport: dict[str, Any] | str) -> bool:
    """True for championship/season futures keys (outrights markets)."""
    key = str(sport.get("key") if isinstance(sport, dict) else sport or "")
    if not key:
        return False
    if isinstance(sport, dict) and not sport.get("active", True):
        return False
    if key.startswith("politics_"):
        return False
    lowered = key.lower()
    return (
        "_winner" in lowered
        or lowered.endswith("_winner")
        or "championship_winner" in lowered
        or "world_series_winner" in lowered
        or "super_bowl_winner" in lowered
    )


def _is_game_sport(sport: dict[str, Any]) -> bool:
    """Active matchup sports — excludes politics and outright/futures keys."""
    if not sport.get("active"):
        return False
    key = str(sport.get("key") or "")
    if not key:
        return False
    if key.startswith("politics_"):
        return False
    if _is_outright_sport(sport):
        return False
    return True


def _sport_label(key: str, sport_title: str | None = None) -> str:
    if key in SPORT_LABELS:
        return SPORT_LABELS[key]
    if sport_title:
        # "NFL Super Bowl Winner" → keep readable for futures tabs
        return sport_title
    parts = key.split("_")
    if len(parts) >= 2:
        return " ".join(p.upper() if len(p) <= 4 else p.title() for p in parts[1:])
    return key.replace("_", " ").title()


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _event_sport_key(event: dict[str, Any]) -> str:
    return str(event.get("_sport_key") or event.get("sport_key") or "")


def _near_term_cache_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Upcoming games within the cache horizon — drops far-future slates (e.g. full NFL season)."""
    raw_count = len(events)
    filtered = filter_upcoming_events(list(events))
    filtered = filter_events_within_horizon(filtered)
    near_keys = {_event_sport_key(e) for e in filtered if _event_sport_key(e)}
    meta = {
        "raw_count": raw_count,
        "near_term_count": len(filtered),
        "dropped_far_out": max(0, raw_count - len(filtered)),
        "near_term_league_keys": sorted(near_keys),
        "near_term_leagues": sorted(
            {str(e.get("_sport_label") or e.get("sport_title") or _sport_label(_event_sport_key(e))) for e in filtered}
        ),
    }
    return filtered, meta


def _event_is_calendar_today(event: dict[str, Any]) -> bool:
    """True when commence_time is later today (US/Eastern)."""
    from app.services.sports_ranking import event_local_date, sports_today

    hours = hours_until_event(event.get("commence_time"))
    if hours is None or hours <= 0:
        return False
    if event.get("_is_outright"):
        return False
    day = event_local_date(event.get("commence_time"))
    return day is not None and day == sports_today()


def calendar_today_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if _event_is_calendar_today(e)]


def _event_is_today_slate(event: dict[str, Any]) -> bool:
    """Next 24 hours of games — the Sports Today window (not midnight-ET only)."""
    hours = hours_until_event(event.get("commence_time"))
    if hours is None or hours <= 0:
        return False
    if event.get("_is_outright"):
        return False
    return hours <= 24 or _event_is_calendar_today(event)


def today_slate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if _event_is_today_slate(e)]


def cache_missing_today_slate(events: list[dict[str, Any]] | None = None) -> bool:
    """True when cached odds have no usable next-24h / Eastern-today games.

    A warm near-term cache of only tomorrow+ games used to make Repair skip live
    Fetch — Today stayed empty on full MLB/WNBA nights.
    """
    if events is None:
        cache = _read_cache()
        events = list(cache.get("events") or []) if cache else []
    upcoming = filter_upcoming_events(list(events))
    today = today_slate_events(upcoming)
    return len(today) == 0


def _essential_keys_for_month() -> frozenset[str]:
    month = datetime.now(UTC).month
    if month in (4, 5, 6, 7, 8, 9):
        return ESSENTIAL_SUMMER_KEYS
    return ESSENTIAL_WINTER_KEYS


def _cache_needs_live_refresh(near_term_keys: frozenset[str]) -> bool:
    """True when cached odds omit enough in-season leagues (e.g. MLB present, WNBA+MLS gone).

    Requires a majority of seasonal essentials — not all — so a single empty rotating
    card (MMA week off / ended preseason) does not force endless live re-fetches.
    """
    if not near_term_keys:
        return True
    core_in_season = _essential_keys_for_month()
    if core_in_season:
        present = len(core_in_season & near_term_keys)
        needed = max(2, (len(core_in_season) + 1) // 2)
        if present < needed:
            return True
    month = datetime.now(UTC).month
    deprioritized = _off_season_deprioritize_keys()
    preferred = SUMMER_PRIORITY_KEYS if month in (4, 5, 6, 7, 8, 9) else WINTER_PRIORITY_KEYS
    expected = {k for k in preferred[:12] if k not in deprioritized}
    return len(near_term_keys & expected) < 3 and len(near_term_keys) <= 4


def _maybe_compact_cache(cache: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
    """Drop far-future noise from a cache payload.

    Never persist an empty compact to disk/remote — that wiped the durable Odds slate
    overnight and left Scan permanently cold until the next live Fetch.
    """
    events = list(cache.get("events") or [])
    if not events:
        return cache
    filtered, meta = _near_term_cache_events(events)
    if meta["dropped_far_out"] <= 0:
        return cache
    logger.info(
        "Compacting odds cache: %d -> %d events (dropped %d far-future)",
        meta["raw_count"],
        meta["near_term_count"],
        meta["dropped_far_out"],
    )
    stats = dict(cache.get("stats") or {})
    stats.update(
        {
            "events_dropped_far_out": meta["dropped_far_out"],
            "leagues_with_near_term_games": meta["near_term_leagues"],
            "cache_compacted": True,
        }
    )
    if not filtered:
        stats["cache_all_past"] = True
        return {
            "fetched_at": cache.get("fetched_at"),
            "events": [],
            "stats": stats,
        }
    if persist:
        _write_cache(filtered, stats)
    return {
        "fetched_at": cache.get("fetched_at"),
        "events": filtered,
        "stats": stats,
    }


def _today_event_count(events: list[dict[str, Any]] | None) -> int:
    if not events:
        return 0
    return len(today_slate_events(filter_upcoming_events(list(events))))


def _cache_today_richer(candidate: dict[str, Any] | None, baseline: dict[str, Any] | None) -> bool:
    """True when candidate has a meaningfully fuller Today slate than baseline."""
    if not candidate or not isinstance(candidate.get("events"), list):
        return False
    cand_today = _today_event_count(list(candidate.get("events") or []))
    base_today = _today_event_count(list((baseline or {}).get("events") or []))
    if cand_today > base_today:
        return True
    if cand_today == 0 and base_today == 0:
        # Fall back to near-term breadth when neither has Tonight yet.
        cand_near, _ = _near_term_cache_events(list(candidate.get("events") or []))
        base_near, _ = _near_term_cache_events(list((baseline or {}).get("events") or []))
        return len(cand_near) > len(base_near)
    return False


def _read_cache() -> dict[str, Any] | None:
    disk_payload: dict[str, Any] | None = None
    try:
        if _CACHE_PATH.exists():
            with _CACHE_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                disk_payload = data
    except (OSError, ValueError) as exc:
        logger.info("Odds cache read failed: %s", exc)

    disk_compacted: dict[str, Any] | None = None
    disk_near: list[dict[str, Any]] = []
    if disk_payload is not None:
        disk_compacted = _maybe_compact_cache(disk_payload, persist=True)
        disk_near, _ = _near_term_cache_events(list(disk_compacted.get("events") or []))
        if not disk_near:
            # Disk is all past / empty after compact — fall through to durable remote.
            logger.info("Odds disk cache has no upcoming events — trying Supabase hydrate")
            disk_compacted = None

    # Disk miss, all-past, OR thin Today slate — hydrate remote and keep the richer Tonight.
    # A warm tomorrow-only disk used to block hydrate and permanently hide Today's games.
    try:
        from app.providers.sports.odds_cache_store import load_remote_cache

        need_remote = disk_compacted is None or cache_missing_today_slate(
            list(disk_compacted.get("events") or [])
        )
        if need_remote:
            remote = load_remote_cache()
            if remote and isinstance(remote.get("events"), list) and remote["events"]:
                remote_compacted = _maybe_compact_cache(remote, persist=False)
                remote_near, _ = _near_term_cache_events(
                    list(remote_compacted.get("events") or [])
                )
                prefer_remote = disk_compacted is None or (
                    bool(remote_near) and _cache_today_richer(remote_compacted, disk_compacted)
                )
                if prefer_remote and remote_near:
                    try:
                        with _CACHE_PATH.open("w", encoding="utf-8") as fh:
                            json.dump(remote_compacted, fh)
                    except (OSError, TypeError) as exc:
                        logger.info("Odds disk hydrate write failed: %s", exc)
                    logger.info(
                        "Odds cache hydrated from Supabase (%s events, today=%s)",
                        len(remote_compacted.get("events") or []),
                        _today_event_count(list(remote_compacted.get("events") or [])),
                    )
                    # Persist compact only when we actually adopt remote (avoid wiping richer remote
                    # via an empty/thin disk compact write-through).
                    return _maybe_compact_cache(remote_compacted, persist=True)
    except Exception as exc:
        logger.info("Odds remote cache hydrate skipped: %s", exc)

    if disk_compacted is not None and disk_near:
        return disk_compacted
    return None


def _write_cache(events: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    payload = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": events,
        "stats": {k: v for k, v in stats.items() if k != "cached"},
    }
    try:
        with _CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except (OSError, TypeError) as exc:
        logger.info("Odds cache write failed: %s", exc)
    # Never write-through an empty slate to Supabase — that permanently kills Scan
    # until the next successful live Fetch after a redeploy.
    if not events:
        return
    try:
        from app.providers.sports.odds_cache_store import load_remote_cache, save_remote_cache

        near, _ = _near_term_cache_events(events)
        new_today = _today_event_count(events)
        # Refuse to clobber a durable Tonight slate with a thinner live/partial write.
        # Scan then rescored the thin disk and wiped the board ("event data loss").
        if new_today > 0 or not near:
            save_remote_cache(payload, near_term_count=len(near))
        else:
            remote = load_remote_cache()
            remote_today = _today_event_count(list((remote or {}).get("events") or []))
            if remote_today > 0 and new_today == 0:
                logger.info(
                    "Odds remote write skipped — local slate has 0 Today games but remote has %s",
                    remote_today,
                )
            else:
                save_remote_cache(payload, near_term_count=len(near))
    except Exception as exc:
        logger.info("Odds remote cache write skipped: %s", exc)


def _invalidate_cache() -> None:
    try:
        _CACHE_PATH.unlink(missing_ok=True)
    except OSError as exc:
        logger.info("Odds cache delete failed: %s", exc)
    try:
        from app.providers.sports.odds_cache_store import clear_remote_cache

        clear_remote_cache()
    except Exception as exc:
        logger.info("Odds remote cache clear skipped: %s", exc)


def _cache_age_minutes(fetched_at: str | None) -> float | None:
    if not fetched_at:
        return None
    try:
        ts = datetime.fromisoformat(fetched_at)
        return (datetime.now(UTC) - ts).total_seconds() / 60
    except ValueError:
        return None


def odds_cache_status() -> dict[str, Any]:
    """Disk cache state — no API credits spent."""
    cache = _read_cache()
    age = _cache_age_minutes(cache.get("fetched_at")) if cache else None
    ttl = max(0, config.settings.odds_cache_ttl_minutes)
    raw_events = list(cache.get("events") or []) if cache else []
    near_term, near_meta = _near_term_cache_events(raw_events) if raw_events else ([], {})
    near_keys = frozenset(near_meta.get("near_term_league_keys") or [])
    needs_live = _cache_needs_live_refresh(near_keys) if near_term else bool(raw_events)
    has_data = bool(near_term)
    within_ttl = age is not None and age <= ttl
    spend_locked = not config.settings.odds_live_spending_allowed()
    # Spend lock: treat any cached upcoming events as rescoreable (0 credits forever).
    if spend_locked and near_term:
        within_ttl = True
    fresh = has_data and within_ttl and not needs_live
    # Matches fetch_all_sports_odds: zero-credit rescore while cache is within TTL.
    rescore_free = bool(cache) and within_ttl and bool(near_term)
    if spend_locked and bool(near_term):
        rescore_free = True
        # Keep needs_live visible — spend lock must not hide a narrow / incomplete slate.
    cache_stats = dict(cache.get("stats") or {}) if cache else {}
    league_catalog = list(cache_stats.get("league_catalog") or [])
    if not league_catalog:
        league_catalog = list(near_meta.get("near_term_leagues") or [])
    today_events = today_slate_events(raw_events) if raw_events else []
    missing_today = not bool(today_events)
    return {
        "has_data": has_data,
        "cache_has_events": bool(raw_events),
        "cache_within_ttl": within_ttl,
        "cache_rescore_free": rescore_free,
        "age_minutes": round(age, 1) if age is not None else None,
        "fresh": fresh,
        "cache_needs_live_refresh": needs_live,
        "missing_today_slate": missing_today,
        "today_event_count": len(today_events),
        "spend_locked": spend_locked,
        "odds_spend_mode": config.settings.odds_spend_mode_normalized(),
        "near_term_event_count": len(near_term),
        "near_term_leagues": list(near_meta.get("near_term_leagues") or []),
        "league_catalog": league_catalog,
        "cache_ttl_minutes": ttl,
        "ttl_minutes": ttl,
        "minutes_until_stale": (
            round(max(0.0, ttl - age), 1) if age is not None and within_ttl else 0.0
        ),
        "event_count": len(raw_events),
        "fetched_at": cache.get("fetched_at") if cache else None,
        "remote_hydrated": bool(cache_stats.get("remote_hydrated")),
        "odds_cache_remote": bool(getattr(config.settings, "odds_cache_remote", True)),
        "stats": cache_stats,
    }


def estimate_live_scan_credits(sport_count: int | None = None) -> int:
    """Rough credits for a live pull: one odds call per sport (/sports list is free)."""
    if sport_count is None:
        max_sports = int(config.settings.odds_max_sports_per_scan or 0)
        if max_sports > 0:
            sport_count = max_sports
        elif config.settings.odds_scan_scope == "full":
            sport_count = len(PRIORITY_SPORT_KEYS) + 8
        else:
            sport_count = min(4, len(CORE_US_LIVE_KEYS))
        if config.settings.odds_include_futures_on_live:
            sport_count += min(6, MAX_FUTURES_SPORTS_PER_SCAN)
    return max(1, int(sport_count))


def _merge_cached_events(
    existing: list[dict[str, Any]],
    refreshed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace only leagues we just fetched; keep other cached leagues (0 extra credits)."""
    refreshed_keys = {
        str(e.get("_sport_key") or "")
        for e in refreshed
        if e.get("_sport_key")
    }
    kept = [
        e
        for e in existing
        if str(e.get("_sport_key") or "") not in refreshed_keys
    ]
    merged = kept + list(refreshed)
    merged = filter_upcoming_events(merged)
    return filter_events_within_horizon(merged)


def _off_season_deprioritize_keys() -> frozenset[str]:
    """Leagues to scan last this month — still included when Odds API marks them active."""
    month = datetime.now(UTC).month
    skip: set[str] = set()
    for months, sport_keys in OFF_SEASON_DEPRIORITIZE_BY_MONTH.items():
        if month in months:
            skip.update(sport_keys)
    return frozenset(skip)


def _off_season_skip_keys() -> frozenset[str]:
    """Deprecated alias — off-season leagues are soft-deprioritized, not skipped."""
    return _off_season_deprioritize_keys()


def _sport_family(key: str) -> str:
    """Top-level family for a sport key, e.g. tennis_atp_wimbledon -> tennis."""
    return str(key).split("_", 1)[0]


def _mix_us_and_global_keys(
    us_keys: tuple[str, ...],
    global_keys: tuple[str, ...],
    *,
    cap: int,
    pinned: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Split a credit cap across US majors and global leagues so neither starves.

    `pinned` keys (usually in-season essentials) always consume slots first.
    """
    if cap <= 0:
        return tuple(dict.fromkeys(list(pinned) + list(us_keys) + list(global_keys)))

    seen: set[str] = set()
    ordered: list[str] = []
    for key in pinned:
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= cap:
            return tuple(ordered)

    remaining = cap - len(ordered)
    us_rest = tuple(k for k in us_keys if k not in seen)
    global_rest = tuple(k for k in global_keys if k not in seen)
    if not global_rest:
        for key in us_rest:
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
            if len(ordered) >= cap:
                break
        return tuple(ordered)
    if not us_rest:
        for key in global_rest:
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
            if len(ordered) >= cap:
                break
        return tuple(ordered)

    # ~60% US / ~40% global of the *remaining* slots after essentials.
    if remaining >= 3:
        global_slots = max(1, min(len(global_rest), round(remaining * 0.4)))
    elif remaining == 2:
        global_slots = 1
    else:
        global_slots = 0
    us_slots = max(0, remaining - global_slots)
    picked_us = list(us_rest[:us_slots])
    leftover = us_slots - len(picked_us)
    picked_global = list(global_rest[: global_slots + leftover])
    leftover_g = (global_slots + leftover) - len(picked_global)
    if leftover_g > 0:
        picked_us = list(us_rest[: us_slots + leftover_g])
    for key in picked_us + picked_global:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= cap:
            break
    return tuple(ordered)


def _essential_keys_available(available: set[str]) -> tuple[str, ...]:
    """In-season essentials that Odds currently lists as active, US-core order first."""
    essential = _essential_keys_for_month()
    if not essential:
        return ()
    ordered: list[str] = []
    seen: set[str] = set()
    for key in CORE_US_LIVE_KEYS:
        if key in essential and key in available and key not in seen:
            ordered.append(key)
            seen.add(key)
    for key in _seasonal_key_order(tuple(essential)):
        if key in available and key not in seen:
            ordered.append(key)
            seen.add(key)
    return tuple(ordered)


def _limit_sport_keys(keys: tuple[str, ...], *, force_refresh: bool = False) -> tuple[str, ...]:
    """Apply scan scope / max-sports. Mix US majors + global leagues within the credit cap."""
    scope = (config.settings.odds_scan_scope or "priority").lower()
    max_sports = int(config.settings.odds_max_sports_per_scan or 0)
    # Routine live Fetch always credit-caps even if env still says full/0.
    tight_live = bool(force_refresh)
    cap = max_sports if max_sports > 0 else (4 if tight_live else 0)

    if tight_live:
        available = set(keys)
        pinned = _essential_keys_available(available)
        us_core = tuple(k for k in CORE_US_LIVE_KEYS if k in available and k not in pinned)
        global_core = tuple(k for k in CORE_GLOBAL_LIVE_KEYS if k in available)
        # Seasonal priority order for globals that aren't already in CORE_GLOBAL.
        seasonal = _seasonal_key_order(tuple(k for k in keys if not is_us_market_sport_key(k)))
        global_ordered = tuple(dict.fromkeys(global_core + seasonal))
        if not pinned and not us_core and not global_ordered:
            fallback = tuple(k for k in keys if k in set(PRIORITY_SPORT_KEYS))
            return fallback[: cap or 4]
        return _mix_us_and_global_keys(
            us_core,
            global_ordered,
            cap=cap or 4,
            pinned=pinned,
        )

    if scope == "priority":
        priority = {k for k in PRIORITY_SPORT_KEYS}
        filtered = tuple(
            k
            for k in keys
            if k in priority or _sport_family(k) in PRIORITY_SPORT_PREFIXES
        )
        if filtered:
            keys = filtered

    keys = _seasonal_key_order(keys)

    deprioritized = _off_season_deprioritize_keys()
    if deprioritized:
        front = tuple(k for k in keys if k not in deprioritized)
        back = tuple(k for k in keys if k in deprioritized)
        keys = front + back

    available = set(keys)
    pinned = _essential_keys_available(available)
    us_keys = tuple(k for k in keys if is_us_market_sport_key(k) and k not in pinned)
    global_keys = tuple(k for k in keys if not is_us_market_sport_key(k))

    if cap > 0:
        return _mix_us_and_global_keys(us_keys, global_keys, cap=cap, pinned=pinned)
    return pinned + us_keys + global_keys


def _seasonal_key_order(keys: tuple[str, ...]) -> tuple[str, ...]:
    month = datetime.now(UTC).month
    preferred = SUMMER_PRIORITY_KEYS if month in (4, 5, 6, 7, 8, 9) else WINTER_PRIORITY_KEYS
    rank = {k: i for i, k in enumerate(preferred)}
    # US book majors first — foreign soccer/tennis used to outrank MLB/WNBA.
    family_boost = {
        "baseball": 0,
        "basketball": 1,
        "americanfootball": 2,
        "icehockey": 3,
        "mma": 4,
        "boxing": 4,
        "soccer": 5,
        "golf": 6,
        "tennis": 7,
        "cricket": 8,
    }

    def _sort_key(k: str) -> tuple[int, int, str]:
        if k in rank:
            return (0, rank[k], k)
        fam = _sport_family(k)
        return (1, family_boost.get(fam, 50), k)

    return tuple(sorted(keys, key=_sort_key))


def filter_events_within_horizon(
    events: list[dict[str, Any]],
    *,
    max_hours: float = MAX_CACHE_HORIZON_HOURS,
) -> list[dict[str, Any]]:
    """Keep upcoming games within the horizon; futures may extend further."""
    out: list[dict[str, Any]] = []
    futures_cap = max(max_hours, 8760)  # ~1 year for championship outrights
    for event in events:
        hours = hours_until_event(event.get("commence_time"))
        if hours is None or hours <= 0:
            continue
        is_futures = bool(event.get("_is_outright")) or _is_outright_sport(
            str(event.get("_sport_key") or event.get("sport_key") or "")
        )
        limit = futures_cap if is_futures else max_hours
        if hours <= limit:
            out.append(event)
    return out


class OddsApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OddsApiClient:
    def __init__(self, api_key: str | None = None, *, timeout: float = 45.0) -> None:
        keys = config.settings.odds_api_keys
        self.api_key = api_key or (keys[0] if keys else "")
        if not self.api_key:
            raise OddsApiError("ODDS_API_KEY is not configured")
        self.timeout = timeout
        self.requests_remaining: str | None = None
        self.requests_used: str | None = None
        self.quota_exhausted: bool = False

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = {"apiKey": self.api_key, **(params or {})}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{ODDS_API_BASE}{path}", params=query)
        except (httpx.HTTPError, OSError) as exc:
            raise OddsApiError(
                f"Cannot reach The Odds API (network/DNS): {exc}",
            ) from exc

        remaining = response.headers.get("x-requests-remaining")
        if remaining is not None:
            self.requests_remaining = remaining
            try:
                if int(remaining) <= 0:
                    self.quota_exhausted = True
            except ValueError:
                pass
        used = response.headers.get("x-requests-used")
        if used is not None:
            self.requests_used = used

        if response.status_code != 200:
            # 401/402 with a zero-remaining quota means the monthly plan is used up.
            if response.status_code in (401, 402) and "usage" in response.text.lower():
                self.quota_exhausted = True
            raise OddsApiError(
                f"Odds API {path} failed: {response.status_code} {response.text[:200]}",
                status_code=response.status_code,
            )
        return response.json()

    async def list_sports(self) -> list[dict[str, Any]]:
        data = await self._get("/sports")
        return data if isinstance(data, list) else []

    async def fetch_odds(
        self,
        sport_key: str,
        *,
        markets: str = "h2h,spreads,totals",
        regions: str = "us",
        bookmakers: str | None = US_BOOKMAKER_KEYS,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": "american",
        }
        # Restrict to FanDuel/DraftKings so scored lines are playable on US books.
        if bookmakers:
            params["bookmakers"] = bookmakers
        data = await self._get(f"/sports/{sport_key}/odds", params)
        return data if isinstance(data, list) else []

    async def fetch_scores(
        self,
        sport_key: str,
        *,
        days_from: int = 7,
    ) -> list[dict[str, Any]]:
        """Completed games with scores — 1 API credit per sport."""
        data = await self._get(
            f"/sports/{sport_key}/scores",
            {"daysFrom": max(1, min(days_from, 3))},
        )
        return data if isinstance(data, list) else []


def _mask_odds_key(key: str) -> str:
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"


# Short-lived cache so the dashboard + sports page share one probe result and
# don't each spawn N network calls. Credits barely change second-to-second, and
# a scan busts this via invalidate_key_probe_cache().
_PROBE_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_PROBE_TTL_SECONDS = 45.0
_PROBE_TIMEOUT_SECONDS = 12.0


def invalidate_key_probe_cache() -> None:
    _PROBE_CACHE["at"] = 0.0
    _PROBE_CACHE["data"] = None


async def _probe_single_key(idx: int, key: str) -> dict[str, Any]:
    """Probe one key via the free /sports endpoint for its live credit count."""
    client = OddsApiClient(key, timeout=_PROBE_TIMEOUT_SECONDS)
    entry: dict[str, Any] = {
        "index": idx + 1,
        "masked": _mask_odds_key(key),
        "remaining": None,
        "used": None,
        "exhausted": False,
        "valid": False,
        "_client": client,
        "_sports": [],
    }
    try:
        sports = await client.list_sports()
        entry["valid"] = True
        entry["_sports"] = sports
        rem = _to_int(client.requests_remaining)
        used = _to_int(client.requests_used)
        if rem is not None:
            entry["remaining"] = rem
        if used is not None:
            entry["used"] = used
        entry["exhausted"] = client.quota_exhausted
    except OddsApiError as exc:
        msg = str(exc)
        entry["error"] = msg[:120]
        if "INVALID_KEY" in msg:
            logger.info("Odds key #%d rejected (invalid)", idx + 1)
        else:
            logger.info("Odds key #%d error: %s", idx + 1, exc)
    return entry


async def probe_all_odds_keys(*, use_cache: bool = True) -> dict[str, Any]:
    """Probe every configured key in parallel via free /sports — sum live credits."""
    keys = config.settings.odds_api_keys
    if not keys:
        return {
            "key_count": 0,
            "keys": [],
            "total_remaining": None,
            "active_key_index": None,
            "active_client": None,
            "active_sports": [],
            "quota_exhausted": False,
            "error": "ODDS_API_KEY is not configured",
        }

    now = _monotonic()
    if (
        use_cache
        and _PROBE_CACHE["data"] is not None
        and (now - _PROBE_CACHE["at"]) < _PROBE_TTL_SECONDS
    ):
        return _PROBE_CACHE["data"]

    probed = await asyncio.gather(*[_probe_single_key(i, k) for i, k in enumerate(keys)])

    total_remaining = 0
    have_remaining = False
    active_index: int | None = None
    active_client: OddsApiClient | None = None
    active_sports: list[dict[str, Any]] = []
    active_remaining = -1
    last_error: str | None = None
    exhausted_valid = 0
    valid_count = 0
    entries: list[dict[str, Any]] = []

    for idx, entry in enumerate(probed):
        client = entry.pop("_client", None)
        sports = entry.pop("_sports", [])
        if entry.get("valid"):
            valid_count += 1
            rem = entry.get("remaining")
            rem_i = int(rem) if rem is not None else -1
            if rem is not None:
                have_remaining = True
                total_remaining += max(0, rem_i)
            if entry.get("exhausted"):
                exhausted_valid += 1
            elif sports and client is not None:
                # Prefer the key with the most remaining credits (not just first valid).
                if active_index is None or rem_i > active_remaining:
                    active_index = idx
                    active_client = client
                    active_sports = sports
                    active_remaining = rem_i
        elif entry.get("error"):
            last_error = entry["error"]
        entries.append(entry)

    quota_exhausted = (
        bool(keys) and valid_count > 0 and exhausted_valid == valid_count and active_index is None
    )

    result = {
        "key_count": len(keys),
        "keys": entries,
        "total_remaining": total_remaining if have_remaining else None,
        "active_key_remaining": active_remaining if active_remaining >= 0 else None,
        "active_key_index": active_index,
        "active_client": active_client,
        "active_sports": active_sports,
        "quota_exhausted": quota_exhausted,
        "error": last_error,
    }

    _PROBE_CACHE["at"] = now
    _PROBE_CACHE["data"] = result
    return result


async def _select_active_client() -> tuple[OddsApiClient | None, list[dict[str, Any]], dict[str, Any]]:
    """Probe each configured key; use the first with quota. Sums credits across all keys."""
    probe = await probe_all_odds_keys()
    client = probe.get("active_client")
    sports = probe.get("active_sports") or []
    info: dict[str, Any] = {
        "key_count": probe["key_count"],
        "active_key_index": probe["active_key_index"],
        "total_remaining": probe["total_remaining"],
        "active_key_remaining": probe.get("active_key_remaining"),
        "quota_exhausted": probe["quota_exhausted"],
        "error": probe.get("error"),
        "keys": probe["keys"],
    }
    if client is not None:
        client.timeout = 45.0  # probe used a short timeout; restore for odds fetches
        info["requests_remaining"] = client.requests_remaining
        info["requests_used"] = client.requests_used
    return client, sports, info


async def resolve_sport_keys() -> tuple[str, ...]:
    """All active game sports from The Odds API (soccer, tennis, US leagues, etc.)."""
    if not config.settings.odds_api_keys:
        return DEFAULT_SPORT_KEYS
    client, sports, _ = await _select_active_client()
    if client is None or not sports:
        return DEFAULT_SPORT_KEYS

    active_game = [s for s in sports if _is_game_sport(s)]
    if not active_game:
        return DEFAULT_SPORT_KEYS

    priority_index = {k: i for i, k in enumerate(PRIORITY_SPORT_KEYS)}
    active_game.sort(
        key=lambda s: (priority_index.get(s["key"], 999), str(s.get("title") or s["key"])),
    )
    return tuple(s["key"] for s in active_game)


def _resolve_futures_keys(all_sports: list[dict[str, Any]]) -> tuple[str, ...]:
    """Active championship/season futures, majors first, capped for credit control."""
    active = [s for s in all_sports if _is_outright_sport(s)]
    if not active:
        return ()
    major = {k for k in MAJOR_FUTURES_KEYS}
    major_first = [s for s in active if s.get("key") in major]
    rest = [s for s in active if s.get("key") not in major]
    major_first.sort(key=lambda s: MAJOR_FUTURES_KEYS.index(s["key"]) if s.get("key") in major else 999)
    rest.sort(key=lambda s: str(s.get("title") or s.get("key") or ""))
    ordered = major_first + rest
    capped = ordered[:MAX_FUTURES_SPORTS_PER_SCAN]
    return tuple(str(s["key"]) for s in capped if s.get("key"))


async def _fetch_sport_odds(
    client: OddsApiClient,
    key: str,
    sport_title: str | None,
    sem: asyncio.Semaphore,
    *,
    outright: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    async with sem:
        label = _sport_label(key, sport_title)
        market_attempts = ("outrights",) if outright else ("h2h,spreads,totals", "h2h")
        for markets in market_attempts:
            try:
                rows = await client.fetch_odds(key, markets=markets)
                for row in rows:
                    row["_sport_label"] = label
                    row["_sport_key"] = key
                    if outright:
                        row["_is_outright"] = True
                        # Normalize missing teams so downstream can detect futures.
                        row.setdefault("home_team", "")
                        row.setdefault("away_team", "")
                if not rows and key in IN_SEASON_RETRY_KEYS and not outright:
                    await asyncio.sleep(0.75)
                    rows = await client.fetch_odds(key, markets=markets)
                    for row in rows:
                        row["_sport_label"] = label
                        row["_sport_key"] = key
                return key, rows
            except OddsApiError as exc:
                if markets == market_attempts[-1]:
                    logger.info("Odds skip %s: %s", key, exc)
                    return key, []
        return key, []


def _stale_cache_response(
    cache: dict[str, Any] | None, info: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Serve last-known odds when every key is spent, so scans still return data."""
    if not cache or not cache.get("events"):
        return None
    age = _cache_age_minutes(cache.get("fetched_at"))
    stats: dict[str, Any] = dict(cache.get("stats") or {})
    stats.update(
        {
            "configured": True,
            "cached": True,
            "stale": True,
            "cache_age_minutes": round(age, 1) if age is not None else None,
            "events": len(cache["events"]),
            "quota_exhausted": True,
            "credits_used": 0,
            "key_count": info.get("key_count"),
            "total_remaining": info.get("total_remaining"),
        }
    )
    return filter_upcoming_events(filter_events_within_horizon(list(cache["events"]))), stats


async def fetch_all_sports_odds(
    sport_keys: tuple[str, ...] | None = None,
    *,
    force_refresh: bool = False,
    cache_only: bool = False,
    bypass_cooldown: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch odds for all active game sports. Returns (events, stats).

    Uses multiple API keys with automatic failover and caches results so
    repeated scans within the TTL cost zero credits.
    """
    if not config.settings.odds_api_keys:
        return [], {"configured": False, "error": "ODDS_API_KEY is not configured"}

    cache = _read_cache()
    spend_locked = not config.settings.odds_live_spending_allowed()
    raw_cached = list(cache.get("events") or []) if cache else []
    near_cached, near_preview = _near_term_cache_events(raw_cached) if raw_cached else ([], {})
    cache_usable = bool(near_cached)
    near_keys = frozenset(near_preview.get("near_term_league_keys") or [])
    incomplete_essentials = bool(near_cached) and _cache_needs_live_refresh(near_keys)
    missing_today = cache_missing_today_slate(raw_cached)
    # Incomplete essentials OR an empty Today slate must be allowed to live-Fetch —
    # cooldown must not trap Repair/Fetch on a warm-looking cache with no tonight games.
    # Only bypass for missing Today — incomplete essentials with tonight games still
    # respect cooldown (Today board already has something to show).
    allow_live_despite_cooldown = missing_today or bypass_cooldown

    # CREDIT SAFETY (hard rules):
    # - Rescore (cache_only) never spends.
    # - Scan (force_refresh=false) never spends under ODDS_SPEND_MODE=cache_only —
    #   serve whatever near-term cache exists, even if narrow. Incomplete slate used
    #   to auto live-seed and burn credits every tap; that is unacceptable.
    # - Only explicit Fetch (force_refresh=true) may spend, and even then a cooldown
    #   blocks rapid re-Fetches when a usable cache already exists.
    serve_cache_only = bool(cache_only) or (spend_locked and not force_refresh)
    if serve_cache_only:
        if not cache_usable:
            return [], {
                "configured": True,
                "cached": False,
                "cache_only": True,
                "spend_locked": spend_locked,
                "odds_spend_mode": config.settings.odds_spend_mode_normalized(),
                "credits_used": 0,
                "cache_needs_live_refresh": True,
                "missing_today_slate": True,
                "today_event_count": 0,
                "error": (
                    "No upcoming games in the odds cache. Tap Fetch live odds ONCE to seed "
                    "FanDuel/DraftKings lines (uses Odds credits). Scan and Rescore stay free after that."
                    if cache and raw_cached
                    else (
                        "No odds cache yet. Tap Fetch live odds ONCE to seed FanDuel/DraftKings lines "
                        "(uses Odds credits). Then use Scan / Rescore for free — do not keep tapping Fetch."
                    )
                ),
            }
        age = _cache_age_minutes(cache.get("fetched_at") if cache else None)
        events, near_meta = _near_term_cache_events(raw_cached)
        near_keys = frozenset(near_meta.get("near_term_league_keys") or [])
        needs_live = _cache_needs_live_refresh(near_keys) if events else bool(raw_cached)
        today_n = len(today_slate_events(raw_cached))
        stats = dict((cache or {}).get("stats") or {})
        stats.update(
            {
                "configured": True,
                "cached": True,
                "cache_only": True,
                "spend_locked": spend_locked,
                "odds_spend_mode": config.settings.odds_spend_mode_normalized(),
                "stale": bool(age is not None and age > max(0, config.settings.odds_cache_ttl_minutes)),
                "cache_age_minutes": round(age, 1) if age is not None else None,
                "events": len(events),
                "events_dropped_past": len(raw_cached) - len(events),
                "events_dropped_far_out": near_meta.get("dropped_far_out", 0),
                "leagues_with_near_term_games": near_meta.get("near_term_leagues") or [],
                "cache_needs_live_refresh": needs_live,
                "missing_today_slate": today_n == 0,
                "today_event_count": today_n,
                "credits_used": 0,
                "scan_scope": "cache_only" if spend_locked else "rescore",
                "max_sports_per_scan": config.settings.odds_max_sports_per_scan,
                "message": (
                    "0 Odds credits — scored from cache. "
                    + (
                        "No games for Today (Eastern) in cache — Repair / Fetch live odds once."
                        if today_n == 0
                        else (
                            "Coverage looks narrow; Fetch live odds once if you need more leagues "
                            "(cooldown protects your credit balance)."
                            if needs_live or incomplete_essentials
                            else "Use Rescore anytime for a free re-rank."
                        )
                    )
                ),
            }
        )
        return events, stats

    # Explicit Fetch cooldown — never burn another ~8 credits seconds after the last pull
    # when we already have upcoming games to Rescore. Bypass when Today is empty or
    # in-season essentials are missing (Repair / Fetch must be able to recover).
    cooldown_min = max(0, int(getattr(config.settings, "odds_live_fetch_cooldown_minutes", 20) or 0))
    if force_refresh and cache_usable and cooldown_min > 0 and not allow_live_despite_cooldown:
        last_live = None
        cache_stats = dict((cache or {}).get("stats") or {})
        last_live_raw = cache_stats.get("last_live_fetch_at") or (cache or {}).get("fetched_at")
        last_live = _cache_age_minutes(str(last_live_raw) if last_live_raw else None)
        if last_live is not None and last_live < cooldown_min:
            wait_m = max(1, int(cooldown_min - last_live))
            events, near_meta = _near_term_cache_events(raw_cached)
            stats = dict(cache_stats)
            stats.update(
                {
                    "configured": True,
                    "cached": True,
                    "cache_only": False,
                    "fetch_cooldown": True,
                    "credits_used": 0,
                    "events": len(events),
                    "leagues_with_near_term_games": near_meta.get("near_term_leagues") or [],
                    "cache_needs_live_refresh": incomplete_essentials,
                    "missing_today_slate": missing_today,
                    "today_event_count": len(today_slate_events(raw_cached)),
                    "message": (
                        f"Fetch cooldown — last live pull was {last_live:.0f}m ago. "
                        f"Served cache (0 credits). Wait ~{wait_m}m or use Rescore / Scan for free."
                    ),
                }
            )
            logger.info("Odds Fetch blocked by %sm cooldown (age=%.1fm)", cooldown_min, last_live)
            return events, stats
    elif force_refresh and allow_live_despite_cooldown:
        logger.info(
            "Odds Fetch bypassing cooldown (missing_today=%s)",
            missing_today,
        )

    # Serve fresh cache without spending any credits (non-spend-locked modes).
    if not force_refresh and cache:
        age = _cache_age_minutes(cache.get("fetched_at"))
        ttl = max(0, config.settings.odds_cache_ttl_minutes)
        if age is not None and age <= ttl:
            raw_events = list(cache.get("events") or [])
            events, near_meta = _near_term_cache_events(raw_events)
            warm_keys = frozenset(near_meta.get("near_term_league_keys") or [])
            needs_live = _cache_needs_live_refresh(warm_keys) if events else bool(raw_events)
            # Never auto live-fill from Scan — incomplete cache is a Fetch hint only.
            if not events and raw_events:
                logger.info(
                    "Odds cache has %d events but none upcoming — invalidating cache",
                    len(raw_events),
                )
                _invalidate_cache()
            stats = dict(cache.get("stats") or {})
            stats.update(
                {
                    "configured": True,
                    "cached": True,
                    "stale": False,
                    "cache_age_minutes": round(age, 1),
                    "events": len(events),
                    "events_dropped_past": len(raw_events) - len(events),
                    "events_dropped_far_out": near_meta.get("dropped_far_out", 0),
                    "leagues_with_near_term_games": near_meta.get("near_term_leagues") or [],
                    "cache_needs_live_refresh": needs_live,
                    "credits_used": 0,
                    "scan_scope": config.settings.odds_scan_scope,
                    "max_sports_per_scan": config.settings.odds_max_sports_per_scan,
                }
            )
            return events, stats

    client, all_sports, info = await _select_active_client()

    # Every key exhausted/invalid → fall back to last-known odds if we have them.
    if client is None:
        stale = _stale_cache_response(cache, info)
        if stale is not None:
            return stale
        return [], {"configured": True, "events": 0, "sports": {}, **info}

    if sport_keys is None:
        title_by_key = {s["key"]: s.get("title") for s in all_sports if s.get("key")}
        active_game = [s for s in all_sports if _is_game_sport(s)]
        priority_index = {k: i for i, k in enumerate(PRIORITY_SPORT_KEYS)}
        active_game.sort(
            key=lambda s: (priority_index.get(s["key"], 999), str(s.get("title") or s["key"])),
        )
        keys = tuple(s["key"] for s in active_game) or DEFAULT_SPORT_KEYS
        # Futures cost extra credits — off unless explicitly enabled.
        include_futures = bool(getattr(config.settings, "odds_include_futures_on_live", False))
        futures_keys = _resolve_futures_keys(all_sports) if include_futures else ()
    else:
        keys = sport_keys
        title_by_key = {s["key"]: s.get("title") for s in all_sports if s.get("key")} if all_sports else {}
        futures_keys = ()

    keys = _limit_sport_keys(keys, force_refresh=force_refresh)
    deprioritized = _off_season_deprioritize_keys()
    stats_deprioritized = sorted(_sport_label(k) for k in deprioritized if k in keys)

    # Credit guard — never start a live pull that would wipe the free-tier budget.
    # Prefer the ACTIVE key's remaining credits (sum across keys overstates what one call can spend).
    remaining = info.get("active_key_remaining")
    if remaining is None:
        remaining = info.get("total_remaining")
    estimated = len(keys) + len(futures_keys)
    reserve = max(0, int(getattr(config.settings, "odds_min_credits_reserve", 15) or 0))
    # Free keys are ~500/mo. A reserve of 500 blocks every live call. Cap auto-reserve,
    # and for intentional Fetch / cold Scan seed keep a tiny cushion so the button works.
    if force_refresh:
        reserve = min(reserve, 2)
    else:
        reserve = min(reserve, 100)
    # Shrink the live slate to fit remaining credits instead of hard-failing cold Scan.
    if remaining is not None and force_refresh and remaining < estimated + reserve:
        affordable = max(0, int(remaining) - reserve)
        if affordable > 0:
            keys = keys[:affordable]
            futures_keys = ()
            estimated = len(keys)
            logger.info(
                "Odds credits tight (%s left) — shrinking live seed to %s leagues",
                remaining,
                estimated,
            )
    if remaining is not None and remaining < estimated + reserve:
        stale = _stale_cache_response(cache, info)
        if stale is not None:
            events, stats = stale
            stats = dict(stats)
            stats.update(
                {
                    "credit_guard": True,
                    "credits_blocked": True,
                    "credits_needed": estimated,
                    "credits_reserve": reserve,
                    "total_remaining": remaining,
                    "message": (
                        f"Odds credits low ({remaining} left; need ~{estimated}+{reserve} reserve). "
                        "Using cached FanDuel/DraftKings lines — Rescore is free. "
                        "OpenAI still ranks picks from cache."
                        if not force_refresh
                        else (
                            f"Odds credits low ({remaining} left; need ~{estimated}+{reserve} for Fetch). "
                            "Served cache instead — add another free Odds key or wait for reset."
                        )
                    ),
                }
            )
            return events, stats
        return [], {
            "configured": True,
            "events": 0,
            "sports": {},
            "credit_guard": True,
            "credits_blocked": True,
            "credits_needed": estimated,
            "total_remaining": remaining,
            "error": (
                f"Odds credits too low for a live scan ({remaining} left). "
                "Wait for quota reset or add another ODDS_API_KEY."
            ),
            **info,
        }

    # League catalog for UI tabs — every scanned game + futures label, seasonally ordered.
    league_catalog = [
        _sport_label(k, title_by_key.get(k)) for k in keys
    ] + [
        _sport_label(k, title_by_key.get(k)) for k in futures_keys
    ]

    events: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "configured": True,
        "cached": False,
        "sports": {},
        "events": 0,
        "sport_keys": list(keys) + list(futures_keys),
        "sports_scanned": len(keys) + len(futures_keys),
        "futures_keys": list(futures_keys),
        "league_catalog": league_catalog,
        "key_count": info.get("key_count"),
        "active_key_index": info.get("active_key_index"),
        "scan_scope": "us_global_live" if force_refresh else config.settings.odds_scan_scope,
        "max_sports_per_scan": config.settings.odds_max_sports_per_scan,
        "bookmakers": US_BOOKMAKER_KEYS,
        # Filled after fetches from leagues that actually returned rows.
        "credits_used": 0,
    }
    if info.get("total_remaining") is not None:
        stats["total_remaining"] = info.get("total_remaining")
    if info.get("active_key_remaining") is not None:
        stats["active_key_remaining"] = info.get("active_key_remaining")

    sem = asyncio.Semaphore(PARALLEL_FETCHES)
    results = await asyncio.gather(
        *[
            _fetch_sport_odds(client, key, title_by_key.get(key), sem, outright=False)
            for key in keys
        ],
        *[
            _fetch_sport_odds(client, key, title_by_key.get(key), sem, outright=True)
            for key in futures_keys
        ],
    )

    leagues_attempted = 0
    leagues_with_rows = 0
    empty_live_keys: list[str] = []
    for key, rows in results:
        leagues_attempted += 1
        events.extend(rows)
        stats["sports"][key] = len(rows)
        if rows:
            leagues_with_rows += 1
        elif key in keys:
            empty_live_keys.append(key)

    # Empty in-season cards (ended NFL preseason / MMA off-week) used to burn the
    # whole 8-league cap and leave Tonight missing soccer/tennis. Backfill with the
    # next priority keys up to the number of empty slots (same credit budget intent).
    if force_refresh and empty_live_keys and sport_keys is None:
        attempted = set(keys) | set(futures_keys)
        # Rebuild uncapped seasonal order from the active catalog, then take fillers.
        title_by_key = title_by_key or {}
        active_game = [s for s in all_sports if _is_game_sport(s)]
        priority_index = {k: i for i, k in enumerate(PRIORITY_SPORT_KEYS)}
        active_game.sort(
            key=lambda s: (priority_index.get(s["key"], 999), str(s.get("title") or s["key"])),
        )
        catalog_keys = tuple(s["key"] for s in active_game) or DEFAULT_SPORT_KEYS
        # Prefer US+global mix without re-pinning the empties we just tried.
        fillers = [
            k
            for k in _limit_sport_keys(catalog_keys, force_refresh=True)
            if k not in attempted
        ]
        # If mix still empty (all essentials failed), walk full seasonal order.
        if not fillers:
            fillers = [k for k in _seasonal_key_order(catalog_keys) if k not in attempted]
        backfill_n = min(len(empty_live_keys), len(fillers))
        backfill_keys = tuple(fillers[:backfill_n])
        if backfill_keys:
            logger.info(
                "Odds live backfill %s leagues after %s empty (%s)",
                len(backfill_keys),
                len(empty_live_keys),
                ",".join(backfill_keys),
            )
            backfill_results = await asyncio.gather(
                *[
                    _fetch_sport_odds(client, key, title_by_key.get(key), sem, outright=False)
                    for key in backfill_keys
                ]
            )
            for key, rows in backfill_results:
                leagues_attempted += 1
                events.extend(rows)
                stats["sports"][key] = len(rows)
                if rows:
                    leagues_with_rows += 1
            keys = tuple(dict.fromkeys(list(keys) + list(backfill_keys)))
            stats["sport_keys"] = list(keys) + list(futures_keys)
            stats["sports_scanned"] = len(keys) + len(futures_keys)
            stats["live_backfill_keys"] = list(backfill_keys)
            stats["league_catalog"] = [
                _sport_label(k, title_by_key.get(k)) for k in keys
            ] + [
                _sport_label(k, title_by_key.get(k)) for k in futures_keys
            ]

    # Count only leagues that returned data as credits spent — empty skips still cost a
    # request, but aspirational credits_used previously marked failed pulls as "live".
    stats["credits_used"] = leagues_attempted
    stats["leagues_with_rows"] = leagues_with_rows

    if client.requests_remaining is not None:
        stats["requests_remaining"] = client.requests_remaining
        # Prefer live remaining after the pull when available.
        stats["total_remaining"] = client.requests_remaining
        stats["active_key_remaining"] = client.requests_remaining
    if client.requests_used is not None:
        stats["requests_used"] = client.requests_used
    if client.quota_exhausted:
        stats["quota_exhausted"] = True

    # A live pull just spent credits — force the next probe to re-read balances.
    invalidate_key_probe_cache()

    raw_count = len(events)
    events = filter_upcoming_events(events)
    events = filter_events_within_horizon(events)
    stats["events_before_horizon"] = raw_count
    stats["events_dropped_far_out"] = max(0, raw_count - len(events))
    stats["events"] = len(events)
    stats["leagues_with_events"] = sorted(
        {_sport_label(k, title_by_key.get(k)) for k, n in stats["sports"].items() if n > 0}
    )
    stats["leagues_with_near_term_games"] = sorted(
        {str(e.get("_sport_label") or e.get("sport_title") or "Sports") for e in events}
    )
    stats["skipped_off_season"] = []
    stats["deprioritized_off_season"] = stats_deprioritized
    stats["today_event_count"] = len(today_slate_events(events))
    stats["missing_today_slate"] = stats["today_event_count"] == 0

    # Merge into existing cache so any live pull doesn't wipe other leagues.
    existing = list(cache.get("events") or []) if cache else []
    if existing and (force_refresh or events):
        events = _merge_cached_events(existing, events)
        stats["cache_merged"] = True
        stats["events"] = len(events)
        stats["leagues_with_near_term_games"] = sorted(
            {str(e.get("_sport_label") or e.get("sport_title") or "Sports") for e in events}
        )
        stats["today_event_count"] = len(today_slate_events(events))
        stats["missing_today_slate"] = stats["today_event_count"] == 0

    if events:
        if int(stats.get("credits_used") or 0) > 0 or (force_refresh and not stats.get("cached")):
            stats["last_live_fetch_at"] = datetime.now(UTC).isoformat()
        _write_cache(events, stats)
    elif force_refresh or not existing:
        # Live pull attempted but produced nothing — surface as a hard error so Scan/Fix all
        # do not pretend Insight has a fresh board to rank.
        stats["error"] = (
            "Live odds pull returned no upcoming FanDuel/DraftKings games. "
            "Check ODDS_API_KEY credits. Prefer Rescore if cache already has games — "
            "do not keep tapping Fetch."
        )
        stats["credits_used"] = 0
        return [], stats

    return events, stats
