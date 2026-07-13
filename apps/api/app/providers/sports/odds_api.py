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


def _essential_keys_for_month() -> frozenset[str]:
    month = datetime.now(UTC).month
    if month in (4, 5, 6, 7, 8, 9):
        return ESSENTIAL_SUMMER_KEYS
    return ESSENTIAL_WINTER_KEYS


def _cache_needs_live_refresh(near_term_keys: frozenset[str]) -> bool:
    """True when cached odds omit in-season leagues (e.g. WNBA missing while MLB present)."""
    if not near_term_keys:
        return True
    core_in_season = _essential_keys_for_month()
    if core_in_season and not core_in_season.issubset(near_term_keys):
        return True
    month = datetime.now(UTC).month
    deprioritized = _off_season_deprioritize_keys()
    preferred = SUMMER_PRIORITY_KEYS if month in (4, 5, 6, 7, 8, 9) else WINTER_PRIORITY_KEYS
    expected = {k for k in preferred[:12] if k not in deprioritized}
    return len(near_term_keys & expected) < 3 and len(near_term_keys) <= 4


def _maybe_compact_cache(cache: dict[str, Any]) -> dict[str, Any]:
    """Rewrite disk cache when it holds mostly far-future noise — no API credits spent."""
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
    _write_cache(filtered, stats)
    return {
        "fetched_at": cache.get("fetched_at"),
        "events": filtered,
        "stats": stats,
    }


def _read_cache() -> dict[str, Any] | None:
    try:
        if not _CACHE_PATH.exists():
            return None
        with _CACHE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return _maybe_compact_cache(data)
    except (OSError, ValueError) as exc:
        logger.info("Odds cache read failed: %s", exc)
    return None


def _write_cache(events: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    try:
        payload = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "events": events,
            "stats": {k: v for k, v in stats.items() if k != "cached"},
        }
        with _CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except (OSError, TypeError) as exc:
        logger.info("Odds cache write failed: %s", exc)


def _invalidate_cache() -> None:
    try:
        _CACHE_PATH.unlink(missing_ok=True)
    except OSError as exc:
        logger.info("Odds cache delete failed: %s", exc)


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
        needs_live = False
    cache_stats = dict(cache.get("stats") or {}) if cache else {}
    league_catalog = list(cache_stats.get("league_catalog") or [])
    if not league_catalog:
        league_catalog = list(near_meta.get("near_term_leagues") or [])
    return {
        "has_data": has_data,
        "cache_has_events": bool(raw_events),
        "cache_within_ttl": within_ttl,
        "cache_rescore_free": rescore_free,
        "age_minutes": round(age, 1) if age is not None else None,
        "fresh": fresh,
        "cache_needs_live_refresh": needs_live,
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
) -> tuple[str, ...]:
    """Split a credit cap across US majors and global leagues so neither starves."""
    if cap <= 0:
        return us_keys + global_keys
    if not global_keys:
        return us_keys[:cap]
    if not us_keys:
        return global_keys[:cap]
    # ~60% US / ~40% global when both pools have active leagues.
    if cap >= 3:
        global_slots = max(1, min(len(global_keys), round(cap * 0.4)))
    elif cap == 2:
        global_slots = 1
    else:
        global_slots = 0
    us_slots = max(1, cap - global_slots)
    picked_us = list(us_keys[:us_slots])
    leftover = us_slots - len(picked_us)
    picked_global = list(global_keys[: global_slots + leftover])
    leftover_g = (global_slots + leftover) - len(picked_global)
    if leftover_g > 0:
        picked_us = list(us_keys[: us_slots + leftover_g])
    seen: set[str] = set()
    ordered: list[str] = []
    for key in picked_us + picked_global:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= cap:
            break
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
        essential = _essential_keys_for_month()
        us_core = tuple(k for k in CORE_US_LIVE_KEYS if k in available)
        us_ordered = tuple(k for k in us_core if k in essential) + tuple(
            k for k in us_core if k not in essential
        )
        global_core = tuple(k for k in CORE_GLOBAL_LIVE_KEYS if k in available)
        # Seasonal priority order for globals that aren't already in CORE_GLOBAL.
        seasonal = _seasonal_key_order(tuple(k for k in keys if not is_us_market_sport_key(k)))
        global_ordered = tuple(dict.fromkeys(global_core + seasonal))
        if not us_ordered and not global_ordered:
            fallback = tuple(k for k in keys if k in set(PRIORITY_SPORT_KEYS))
            return fallback[: cap or 4]
        return _mix_us_and_global_keys(us_ordered, global_ordered, cap=cap or 4)

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

    essential = _essential_keys_for_month()
    us_keys = tuple(k for k in keys if is_us_market_sport_key(k))
    global_keys = tuple(k for k in keys if not is_us_market_sport_key(k))
    us_ordered = tuple(k for k in us_keys if k in essential) + tuple(
        k for k in us_keys if k not in essential
    )

    if cap > 0:
        return _mix_us_and_global_keys(us_ordered, global_keys, cap=cap)
    return us_ordered + global_keys


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
    last_error: str | None = None
    exhausted_valid = 0
    valid_count = 0
    entries: list[dict[str, Any]] = []

    for idx, entry in enumerate(probed):
        client = entry.pop("_client", None)
        sports = entry.pop("_sports", [])
        if entry.get("valid"):
            valid_count += 1
            if entry.get("remaining") is not None:
                have_remaining = True
                total_remaining += max(0, int(entry["remaining"]))
            if entry.get("exhausted"):
                exhausted_valid += 1
            elif active_index is None and sports and client is not None:
                active_index = idx
                active_client = client
                active_sports = sports
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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch odds for all active game sports. Returns (events, stats).

    Uses multiple API keys with automatic failover and caches results so
    repeated scans within the TTL cost zero credits.
    """
    if not config.settings.odds_api_keys:
        return [], {"configured": False, "error": "ODDS_API_KEY is not configured"}

    cache = _read_cache()
    spend_locked = not config.settings.odds_live_spending_allowed()
    # cache_only (Rescore) never spends. Spend-lock blocks automatic pulls, but
    # explicit Fetch live odds (force_refresh) is still allowed so the board can
    # be refreshed without unlocking global auto-spend.
    block_live = cache_only or (spend_locked and not force_refresh)
    if block_live:
        if not cache or not cache.get("events"):
            return [], {
                "configured": True,
                "cached": False,
                "cache_only": True,
                "spend_locked": spend_locked,
                "odds_spend_mode": config.settings.odds_spend_mode_normalized(),
                "credits_used": 0,
                "error": (
                    "No odds cache yet. Tap Fetch live odds once to seed FanDuel/DraftKings lines "
                    "(uses a few Odds credits). Rescore / Scan stay free after that."
                    if spend_locked and not force_refresh
                    else (
                        "Odds spend lock is on (cache-only) and there is no odds cache yet. "
                        "Set ODDS_SPEND_MODE=conservative after adding fresh keys, then Fetch once — "
                        "or keep using Atlas Insight / Search from OpenAI."
                    )
                ),
            }
        age = _cache_age_minutes(cache.get("fetched_at"))
        raw_events = list(cache.get("events") or [])
        events, near_meta = _near_term_cache_events(raw_events)
        near_keys = frozenset(near_meta.get("near_term_league_keys") or [])
        needs_live = _cache_needs_live_refresh(near_keys) if events else bool(raw_events)
        stats = dict(cache.get("stats") or {})
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
                "events_dropped_past": len(raw_events) - len(events),
                "events_dropped_far_out": near_meta.get("dropped_far_out", 0),
                "leagues_with_near_term_games": near_meta.get("near_term_leagues") or [],
                "cache_needs_live_refresh": False if spend_locked else needs_live,
                "credits_used": 0,
                "scan_scope": "cache_only" if spend_locked else "rescore",
                "max_sports_per_scan": config.settings.odds_max_sports_per_scan,
                "message": (
                    "Odds auto-spend is locked — served cached lines (0 credits). "
                    "Tap Fetch live odds when you want a fresh slate."
                    if spend_locked
                    else None
                ),
            }
        )
        return events, stats

    # Serve fresh cache without spending any credits.
    if not force_refresh and cache:
        age = _cache_age_minutes(cache.get("fetched_at"))
        ttl = max(0, config.settings.odds_cache_ttl_minutes)
        if age is not None and age <= ttl:
            raw_events = list(cache.get("events") or [])
            events, near_meta = _near_term_cache_events(raw_events)
            near_keys = frozenset(near_meta.get("near_term_league_keys") or [])
            needs_live = _cache_needs_live_refresh(near_keys) if events else bool(raw_events)
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
    remaining = info.get("total_remaining")
    estimated = len(keys) + len(futures_keys)
    reserve = max(0, int(getattr(config.settings, "odds_min_credits_reserve", 15) or 0))
    # Free keys are ~500/mo. A reserve of 500 blocks every live call. Cap auto-reserve,
    # and for intentional Fetch only keep a tiny cushion so the button works.
    if force_refresh:
        reserve = min(reserve, 10)
    else:
        reserve = min(reserve, 100)
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
        # /sports is free — only per-league odds calls cost credits.
        "credits_used": len(keys) + len(futures_keys),
    }
    if info.get("total_remaining") is not None:
        stats["total_remaining"] = info.get("total_remaining")

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

    for key, rows in results:
        events.extend(rows)
        stats["sports"][key] = len(rows)

    if client.requests_remaining is not None:
        stats["requests_remaining"] = client.requests_remaining
        # Prefer live remaining after the pull when available.
        stats["total_remaining"] = client.requests_remaining
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

    # Merge into existing cache so priority live Fetch doesn't wipe other leagues.
    existing = list(cache.get("events") or []) if cache else []
    if force_refresh and existing:
        events = _merge_cached_events(existing, events)
        stats["cache_merged"] = True
        stats["events"] = len(events)
        stats["leagues_with_near_term_games"] = sorted(
            {str(e.get("_sport_label") or e.get("sport_title") or "Sports") for e in events}
        )

    if events:
        _write_cache(events, stats)

    return events, stats
