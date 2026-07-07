"""Grade sports picks against final scores."""

from __future__ import annotations

import re
from typing import Any


def unit_bet_return_pct(american: int, won: bool) -> float:
    if not won:
        return -100.0
    if american > 0:
        return float(american)
    return round(100 / abs(american) * 100, 2)


def _parse_score(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _team_in_selection(team: str, selection: str) -> bool:
    if not team or not selection:
        return False
    return team.lower() in selection.lower()


def _parse_spread_selection(selection: str) -> tuple[str | None, float | None]:
    match = re.match(r"^(.+?)\s+([+-]?\d+(?:\.\d+)?)$", selection.strip())
    if not match:
        return None, None
    return match.group(1).strip(), float(match.group(2))


def _parse_total_selection(selection: str) -> tuple[str | None, float | None]:
    match = re.match(r"^(Over|Under)\s+(\d+(?:\.\d+)?)$", selection.strip(), re.I)
    if not match:
        return None, None
    return match.group(1).title(), float(match.group(2))


def grade_sports_pick(
    signal: dict[str, Any],
    *,
    home_score: int,
    away_score: int,
    home_team: str,
    away_team: str,
) -> tuple[str, float] | None:
    """Return (outcome, return_pct) or None if ungradable."""
    bet_type = str(signal.get("bet_type") or "").lower()
    selection = str(signal.get("selection") or "")
    odds = int(signal.get("odds_american") or -110)
    snap = signal.get("scoring_snapshot") or {}
    pick = snap.get("pick") or {}
    raw_side = str(pick.get("team_or_side") or "")
    raw_point = pick.get("point")

    total_pts = home_score + away_score

    if bet_type == "moneyline":
        team = raw_side or selection
        if _team_in_selection(home_team, team):
            won = home_score > away_score
        elif _team_in_selection(away_team, team):
            won = away_score > home_score
        else:
            return None
        if home_score == away_score:
            return "scratch", 0.0
        outcome = "win" if won else "loss"
        return outcome, unit_bet_return_pct(odds, won)

    if bet_type == "spread":
        team_name, point = _parse_spread_selection(selection)
        if point is None and raw_point is not None:
            point = float(raw_point)
            team_name = raw_side or team_name
        if point is None or not team_name:
            return None
        if _team_in_selection(home_team, team_name):
            adjusted = home_score + point
            opp = away_score
        elif _team_in_selection(away_team, team_name):
            adjusted = away_score + point
            opp = home_score
        else:
            return None
        if adjusted > opp:
            return "win", unit_bet_return_pct(odds, True)
        if adjusted < opp:
            return "loss", unit_bet_return_pct(odds, False)
        return "scratch", 0.0

    if bet_type == "total":
        side, line = _parse_total_selection(selection)
        if line is None and raw_point is not None:
            line = float(raw_point)
            side = raw_side.title() if raw_side else side
        if line is None or not side:
            return None
        if side == "Over":
            won = total_pts > line
            push = total_pts == line
        else:
            won = total_pts < line
            push = total_pts == line
        if push:
            return "scratch", 0.0
        outcome = "win" if won else "loss"
        return outcome, unit_bet_return_pct(odds, won)

    return None


def match_completed_game(
    signal: dict[str, Any],
    games: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find a completed scores API row for this signal."""
    snap = signal.get("scoring_snapshot") or {}
    line_mv = signal.get("line_movement") or {}
    event_id = snap.get("event_id") or line_mv.get("event_id")
    home = snap.get("home_team") or ""
    away = snap.get("away_team") or ""

    if not home and signal.get("event_name"):
        parts = str(signal.get("event_name")).split("@")
        if len(parts) == 2:
            away = parts[0].strip()
            home = parts[1].strip()

    for game in games:
        if not game.get("completed"):
            continue
        if event_id and game.get("id") == event_id:
            return game
        g_home = str(game.get("home_team") or "")
        g_away = str(game.get("away_team") or "")
        if home and away and g_home == home and g_away == away:
            return game
    return None


def scores_from_game(game: dict[str, Any]) -> tuple[int, int, str, str] | None:
    home_team = str(game.get("home_team") or "")
    away_team = str(game.get("away_team") or "")
    home_score = away_score = None
    for entry in game.get("scores") or []:
        name = str(entry.get("name") or "")
        if name == home_team:
            home_score = _parse_score(entry.get("score"))
        elif name == away_team:
            away_score = _parse_score(entry.get("score"))
    if home_score is None or away_score is None:
        return None
    return home_score, away_score, home_team, away_team
