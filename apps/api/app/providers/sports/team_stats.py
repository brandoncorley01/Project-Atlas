"""Team form and head-to-head stats from Odds API completed scores."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.sports.odds_api import OddsApiError, _select_active_client

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parents[3] / ".scores_cache.json"
_CACHE_TTL_HOURS = 6
_RECENT_GAMES = 10
_SCORES_DAYS = 3

# Sports where scores endpoint returns useful team-level results.
# Tennis/golf rotate tournament keys — match by family in the fetch helper.
_SCORES_SPORTS = frozenset(
    {
        "americanfootball_nfl",
        "americanfootball_nfl_preseason",
        "americanfootball_ncaaf",
        "americanfootball_cfl",
        "basketball_nba",
        "basketball_wnba",
        "basketball_ncaab",
        "basketball_wncaab",
        "baseball_mlb",
        "icehockey_nhl",
        "soccer_epl",
        "soccer_usa_mls",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_fifa_world_cup",
        "soccer_mexico_ligamx",
        "soccer_brazil_campeonato",
        "mma_mixed_martial_arts",
        "boxing_boxing",
        "tennis_atp_wimbledon",
        "tennis_wta_wimbledon",
        "tennis_atp_us_open",
        "tennis_wta_us_open",
    }
)
_SCORES_SPORT_PREFIXES = frozenset({"tennis", "soccer", "mma", "boxing"})


def _scores_key_allowed(key: str) -> bool:
    if key in _SCORES_SPORTS:
        return True
    family = key.split("_", 1)[0]
    return family in _SCORES_SPORT_PREFIXES


@dataclass
class TeamForm:
    name: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    games_sampled: int = 0
    avg_scored: float | None = None
    avg_allowed: float | None = None
    recent_results: list[str] = field(default_factory=list)
    home_wins: int = 0
    home_losses: int = 0
    away_wins: int = 0
    away_losses: int = 0

    @property
    def win_pct(self) -> float:
        total = self.wins + self.losses + self.draws
        if total <= 0:
            return 0.5
        return self.wins / total

    def record_label(self) -> str:
        if self.draws:
            return f"{self.wins}-{self.losses}-{self.draws}"
        return f"{self.wins}-{self.losses}"

    def form_label(self) -> str:
        if not self.recent_results:
            return "no recent games"
        return "".join(self.recent_results[:5])


@dataclass
class MatchStats:
    home_team: str
    away_team: str
    home: TeamForm
    away: TeamForm
    h2h_home_wins: int = 0
    h2h_away_wins: int = 0
    h2h_draws: int = 0
    h2h_games: int = 0
    sample_games: int = 0

    def summary(self) -> str:
        parts = [
            f"{self.home.name} {self.home.record_label()} (L{self.home.games_sampled})",
            f"{self.away.name} {self.away.record_label()} (L{self.away.games_sampled})",
        ]
        if self.h2h_games:
            parts.append(
                f"H2H {self.h2h_home_wins}-{self.h2h_away_wins}"
                + (f"-{self.h2h_draws}" if self.h2h_draws else "")
            )
        return " · ".join(parts)


def normalize_team(name: str) -> str:
    text = str(name or "").lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    for suffix in (" football club", " fc", " cf", " united", " city", " sc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _parse_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _game_result(home_score: float, away_score: float) -> tuple[str, str]:
    if home_score > away_score:
        return "W", "L"
    if away_score > home_score:
        return "L", "W"
    return "D", "D"


def _read_cache() -> dict[str, Any] | None:
    try:
        if not _CACHE_PATH.exists():
            return None
        with _CACHE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        logger.info("Scores cache read failed: %s", exc)
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    try:
        with _CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except (OSError, TypeError) as exc:
        logger.info("Scores cache write failed: %s", exc)


def _cache_fresh(fetched_at: str | None) -> bool:
    if not fetched_at:
        return False
    try:
        ts = datetime.fromisoformat(fetched_at)
        age_h = (datetime.now(UTC) - ts).total_seconds() / 3600
        return age_h <= _CACHE_TTL_HOURS
    except ValueError:
        return False


def _ingest_completed_games(games: list[dict[str, Any]]) -> dict[str, TeamForm]:
    """Build per-team form from completed score rows."""
    teams: dict[str, TeamForm] = {}
    h2h: dict[tuple[str, str], list[tuple[float, float]]] = {}

    sorted_games = sorted(
        [g for g in games if g.get("completed")],
        key=lambda g: str(g.get("commence_time") or ""),
        reverse=True,
    )

    for game in sorted_games:
        home_name = str(game.get("home_team") or "")
        away_name = str(game.get("away_team") or "")
        if not home_name or not away_name:
            continue

        scores = game.get("scores") or []
        home_score = None
        away_score = None
        for entry in scores:
            name = str(entry.get("name") or "")
            if name == home_name:
                home_score = _parse_score(entry.get("score"))
            elif name == away_name:
                away_score = _parse_score(entry.get("score"))
        if home_score is None or away_score is None:
            continue

        home_key = normalize_team(home_name)
        away_key = normalize_team(away_name)
        h2h.setdefault((home_key, away_key), []).append((home_score, away_score))

        for display_name, key, scored, allowed, venue in (
            (home_name, home_key, home_score, away_score, "home"),
            (away_name, away_key, away_score, home_score, "away"),
        ):
            form = teams.setdefault(key, TeamForm(name=display_name))
            if form.games_sampled >= _RECENT_GAMES:
                continue
            form.games_sampled += 1
            res_home, res_away = _game_result(home_score, away_score)
            result = res_home if venue == "home" else res_away
            form.recent_results.append(result)
            if result == "W":
                form.wins += 1
            elif result == "L":
                form.losses += 1
            else:
                form.draws += 1
            if venue == "home":
                if result == "W":
                    form.home_wins += 1
                elif result == "L":
                    form.home_losses += 1
            else:
                if result == "W":
                    form.away_wins += 1
                elif result == "L":
                    form.away_losses += 1
            if form.avg_scored is None:
                form.avg_scored = scored
                form.avg_allowed = allowed
            else:
                n = form.games_sampled
                form.avg_scored = ((form.avg_scored or 0) * (n - 1) + scored) / n
                form.avg_allowed = ((form.avg_allowed or 0) * (n - 1) + allowed) / n

    return teams


def _h2h_for_match(
    home: str,
    away: str,
    games: list[dict[str, Any]],
) -> tuple[int, int, int, int]:
    home_key = normalize_team(home)
    away_key = normalize_team(away)
    hw = aw = dr = 0
    count = 0
    for game in games:
        if not game.get("completed"):
            continue
        g_home = normalize_team(str(game.get("home_team") or ""))
        g_away = normalize_team(str(game.get("away_team") or ""))
        if not ((g_home == home_key and g_away == away_key) or (g_home == away_key and g_away == home_key)):
            continue
        scores = game.get("scores") or []
        hs = as_ = None
        for entry in scores:
            name = str(entry.get("name") or "")
            if name == game.get("home_team"):
                hs = _parse_score(entry.get("score"))
            elif name == game.get("away_team"):
                as_ = _parse_score(entry.get("score"))
        if hs is None or as_ is None:
            continue
        count += 1
        if g_home == home_key:
            if hs > as_:
                hw += 1
            elif as_ > hs:
                aw += 1
            else:
                dr += 1
        else:
            if as_ > hs:
                hw += 1
            elif hs > as_:
                aw += 1
            else:
                dr += 1
    return hw, aw, dr, count


def build_match_stats(home: str, away: str, team_index: dict[str, TeamForm], games: list[dict[str, Any]]) -> MatchStats:
    home_key = normalize_team(home)
    away_key = normalize_team(away)
    home_form = team_index.get(home_key) or TeamForm(name=home)
    away_form = team_index.get(away_key) or TeamForm(name=away)
    hw, aw, dr, h2h_n = _h2h_for_match(home, away, games)
    return MatchStats(
        home_team=home,
        away_team=away,
        home=home_form,
        away=away_form,
        h2h_home_wins=hw,
        h2h_away_wins=aw,
        h2h_draws=dr,
        h2h_games=h2h_n,
        sample_games=home_form.games_sampled + away_form.games_sampled,
    )


def _team_form_dict(form: TeamForm) -> dict[str, Any]:
    return {
        "name": form.name,
        "record": form.record_label(),
        "win_pct": round(form.win_pct * 100, 1),
        "form": form.form_label(),
        "games_sampled": form.games_sampled,
        "avg_scored": round(form.avg_scored, 1) if form.avg_scored is not None else None,
        "avg_allowed": round(form.avg_allowed, 1) if form.avg_allowed is not None else None,
        "home_record": f"{form.home_wins}-{form.home_losses}",
        "away_record": f"{form.away_wins}-{form.away_losses}",
    }


def match_stats_payload(stats: MatchStats | None) -> dict[str, Any] | None:
    if stats is None or stats.sample_games < 2:
        return None
    return {
        "home": _team_form_dict(stats.home),
        "away": _team_form_dict(stats.away),
        "h2h": {
            "home_wins": stats.h2h_home_wins,
            "away_wins": stats.h2h_away_wins,
            "draws": stats.h2h_draws,
            "games": stats.h2h_games,
        },
        "summary": stats.summary(),
    }


async def fetch_scores_by_sport(sport_keys: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Fetch recent completed scores per sport (cached)."""
    keys = {k for k in sport_keys if _scores_key_allowed(k)}
    if not keys:
        return {}

    cache = _read_cache()
    if cache and _cache_fresh(cache.get("fetched_at")):
        by_sport = cache.get("by_sport") or {}
        return {k: list(by_sport.get(k) or []) for k in keys if k in by_sport}

    client, _, _ = await _select_active_client()
    if client is None:
        if cache:
            by_sport = cache.get("by_sport") or {}
            return {k: list(by_sport.get(k) or []) for k in keys if k in by_sport}
        return {}

    by_sport: dict[str, list[dict[str, Any]]] = dict(cache.get("by_sport") or {}) if cache else {}
    sem = asyncio.Semaphore(6)

    async def _pull(key: str) -> None:
        async with sem:
            try:
                rows = await client.fetch_scores(key, days_from=_SCORES_DAYS)
                completed = [r for r in rows if r.get("completed")]
                if completed:
                    by_sport[key] = completed
            except (OddsApiError, OSError) as exc:
                logger.info("Scores skip %s: %s", key, exc)

    await asyncio.gather(*[_pull(k) for k in keys])
    _write_cache({"fetched_at": datetime.now(UTC).isoformat(), "by_sport": by_sport})
    return {k: list(by_sport.get(k) or []) for k in keys}


async def build_stats_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """sport_key -> {team_index, games, match_lookup helper data}."""
    sport_keys = {str(e.get("_sport_key") or "") for e in events if e.get("_sport_key")}
    scores_by_sport = await fetch_scores_by_sport(sport_keys)
    index: dict[str, dict[str, Any]] = {}
    for sport_key, games in scores_by_sport.items():
        index[sport_key] = {
            "team_index": _ingest_completed_games(games),
            "games": games,
        }
    return index


def lookup_match_stats(event: dict[str, Any], stats_index: dict[str, dict[str, Any]]) -> MatchStats | None:
    sport_key = str(event.get("_sport_key") or "")
    bucket = stats_index.get(sport_key)
    if not bucket:
        return None
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    if not home or not away:
        return None
    return build_match_stats(home, away, bucket["team_index"], bucket["games"])
