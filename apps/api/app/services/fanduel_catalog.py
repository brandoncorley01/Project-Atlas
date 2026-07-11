"""FanDuel-verified bet catalog for Atlas Insight — never invent markets."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app import config
from app.agents.sports_analyst import PREFERRED_BOOK_KEY, US_PREFERRED_BOOK_KEYS
from app.providers.sports.odds_api import (
    OddsApiClient,
    OddsApiError,
    _read_cache,
    _select_active_client,
    invalidate_key_probe_cache,
)
from app.services.freshness import filter_upcoming_events, hours_until_event

logger = logging.getLogger(__name__)

# Credit-safe prop market allowlists (each market key = 1 Odds credit per event).
PROP_MARKETS_BY_SPORT: dict[str, tuple[str, ...]] = {
    "baseball_mlb": ("batter_hits", "batter_home_runs", "pitcher_strikeouts"),
    "basketball_wnba": ("player_points", "player_rebounds", "player_assists"),
    "basketball_nba": ("player_points", "player_rebounds", "player_assists"),
    "americanfootball_nfl": ("player_pass_yds", "player_rush_yds", "player_receptions"),
    "icehockey_nhl": ("player_points", "player_shots_on_goal"),
}

PROP_MARKET_LABELS: dict[str, str] = {
    "batter_hits": "Hits",
    "batter_home_runs": "Home runs",
    "pitcher_strikeouts": "Strikeouts",
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_pass_yds": "Pass yards",
    "player_rush_yds": "Rush yards",
    "player_receptions": "Receptions",
    "player_shots_on_goal": "Shots",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _fanduel_books(event: dict[str, Any]) -> list[dict[str, Any]]:
    books = [b for b in (event.get("bookmakers") or []) if str(b.get("key") or "") in US_PREFERRED_BOOK_KEYS]
    books.sort(key=lambda b: 0 if b.get("key") == PREFERRED_BOOK_KEY else 1)
    return books or list(event.get("bookmakers") or [])


def _append_game_lines(catalog: list[dict[str, Any]], event: dict[str, Any]) -> None:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    if not home or not away:
        return
    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    sport_key = str(event.get("_sport_key") or event.get("sport_key") or "")
    event_id = str(event.get("id") or "")
    event_name = f"{away} @ {home}"
    start = event.get("commence_time")

    for book in _fanduel_books(event)[:1]:  # FanDuel first only for verification
        book_key = str(book.get("key") or PREFERRED_BOOK_KEY)
        book_title = str(book.get("title") or "FanDuel")
        for market in book.get("markets") or []:
            mkey = str(market.get("key") or "")
            bet_type = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}.get(mkey)
            if not bet_type:
                continue
            for outcome in market.get("outcomes") or []:
                name = str(outcome.get("name") or "").strip()
                if not name:
                    continue
                try:
                    american = int(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                point = outcome.get("point")
                try:
                    point_f = float(point) if point is not None else None
                except (TypeError, ValueError):
                    point_f = None
                if bet_type == "spread" and point_f is not None:
                    sign = "+" if point_f > 0 else ""
                    selection = f"{name} {sign}{point_f:g}"
                elif bet_type == "total" and point_f is not None:
                    selection = f"{name} {point_f:g}"
                else:
                    selection = name
                catalog.append(
                    {
                        "sport": sport,
                        "sport_key": sport_key,
                        "event_id": event_id,
                        "event_name": event_name,
                        "event_start": start,
                        "home_team": home,
                        "away_team": away,
                        "bet_type": bet_type,
                        "selection": selection,
                        "odds_american": american,
                        "point": point_f,
                        "book_key": book_key,
                        "book_title": book_title,
                        "prop_market": None,
                        "player_name": None,
                        "fanduel_verified": True,
                    }
                )


def _prop_selection(market_key: str, outcome: dict[str, Any]) -> tuple[str, str | None, float | None]:
    """Build FanDuel-style prop selection from Odds API outcome."""
    side = str(outcome.get("name") or "").strip()  # Over / Under / Yes / No
    player = str(outcome.get("description") or "").strip() or None
    point = outcome.get("point")
    try:
        point_f = float(point) if point is not None else None
    except (TypeError, ValueError):
        point_f = None
    label = PROP_MARKET_LABELS.get(market_key, market_key.replace("_", " ").title())
    if player and point_f is not None and side:
        selection = f"{player} {side} {point_f:g} {label}"
    elif player and side:
        selection = f"{player} {side} {label}"
    else:
        selection = f"{side} {label}".strip()
    return selection, player, point_f


def _append_prop_markets(catalog: list[dict[str, Any]], event: dict[str, Any]) -> None:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    sport_key = str(event.get("_sport_key") or event.get("sport_key") or "")
    event_id = str(event.get("id") or "")
    event_name = f"{away} @ {home}" if home and away else str(event.get("event_name") or "Event")
    start = event.get("commence_time")

    for book in _fanduel_books(event):
        if str(book.get("key") or "") != PREFERRED_BOOK_KEY and any(
            str(b.get("key")) == PREFERRED_BOOK_KEY for b in _fanduel_books(event)
        ):
            continue
        book_key = str(book.get("key") or PREFERRED_BOOK_KEY)
        book_title = str(book.get("title") or "FanDuel")
        for market in book.get("markets") or []:
            mkey = str(market.get("key") or "")
            if mkey not in PROP_MARKET_LABELS and not mkey.startswith(("batter_", "pitcher_", "player_")):
                continue
            if mkey in {"h2h", "spreads", "totals", "outrights"}:
                continue
            for outcome in market.get("outcomes") or []:
                try:
                    american = int(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                selection, player, point_f = _prop_selection(mkey, outcome)
                if not selection:
                    continue
                catalog.append(
                    {
                        "sport": sport,
                        "sport_key": sport_key,
                        "event_id": event_id,
                        "event_name": event_name,
                        "event_start": start,
                        "home_team": home,
                        "away_team": away,
                        "bet_type": "player_prop",
                        "selection": selection,
                        "odds_american": american,
                        "point": point_f,
                        "book_key": book_key,
                        "book_title": book_title,
                        "prop_market": mkey,
                        "player_name": player,
                        "fanduel_verified": True,
                    }
                )


async def _fetch_event_props(
    client: OddsApiClient,
    *,
    sport_key: str,
    event_id: str,
    markets: tuple[str, ...],
) -> dict[str, Any] | None:
    """Event odds endpoint — required for player props. Costs 1 credit per market."""
    if not event_id or not markets:
        return None
    try:
        data = await client._get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {
                "regions": "us",
                "markets": ",".join(markets),
                "oddsFormat": "american",
                "bookmakers": PREFERRED_BOOK_KEY,
            },
        )
        return data if isinstance(data, dict) else None
    except OddsApiError as exc:
        logger.info("FanDuel props skip %s/%s: %s", sport_key, event_id[:8], exc)
        return None


def _soon_events_for_props(events: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    eligible = []
    for e in events:
        sport_key = str(e.get("_sport_key") or e.get("sport_key") or "")
        if sport_key not in PROP_MARKETS_BY_SPORT:
            continue
        if e.get("_is_outright"):
            continue
        if not e.get("id") or not e.get("home_team"):
            continue
        hours = hours_until_event(e.get("commence_time"))
        if hours is None or hours <= 0 or hours > 48:
            continue
        eligible.append((hours, e))
    eligible.sort(key=lambda x: x[0])
    return [e for _, e in eligible[:limit]]


async def build_fanduel_catalog(
    *,
    include_props: bool = True,
    max_prop_events: int | None = None,
) -> dict[str, Any]:
    """Build a FanDuel-only catalog: game lines from cache + capped live props."""
    cache = _read_cache()
    events = filter_upcoming_events(list(cache.get("events") or [])) if cache else []
    events = [e for e in events if not e.get("_is_outright")]

    catalog: list[dict[str, Any]] = []
    for event in events:
        _append_game_lines(catalog, event)

    credits_used = 0
    props_events = 0
    prop_cap = max_prop_events
    if prop_cap is None:
        prop_cap = int(getattr(config.settings, "odds_insight_prop_events", 2) or 2)
    prop_cap = max(0, min(prop_cap, 4))

    remaining_credits: int | None = None
    if include_props and prop_cap > 0 and events:
        client, _, info = await _select_active_client()
        remaining_credits = info.get("total_remaining")
        reserve = max(0, int(getattr(config.settings, "odds_insight_min_credits_reserve", 5) or 0))
        # Each event costs len(markets) credits.
        soon = _soon_events_for_props(events, limit=prop_cap)
        for event in soon:
            sport_key = str(event.get("_sport_key") or "")
            markets = PROP_MARKETS_BY_SPORT.get(sport_key) or ()
            if not markets or not client:
                break
            cost = len(markets)
            if remaining_credits is not None and remaining_credits < cost + reserve:
                logger.info(
                    "Atlas Insight props skipped — credits low (%s left, need %s+%s)",
                    remaining_credits,
                    cost,
                    reserve,
                )
                break
            payload = await _fetch_event_props(
                client,
                sport_key=sport_key,
                event_id=str(event.get("id") or ""),
                markets=markets,
            )
            credits_used += cost
            if remaining_credits is not None:
                remaining_credits = max(0, remaining_credits - cost)
            if not payload:
                continue
            # Merge sport metadata onto event-odds payload.
            payload["_sport_key"] = sport_key
            payload["_sport_label"] = event.get("_sport_label") or event.get("sport_title")
            payload.setdefault("home_team", event.get("home_team"))
            payload.setdefault("away_team", event.get("away_team"))
            payload.setdefault("commence_time", event.get("commence_time"))
            before = len(catalog)
            _append_prop_markets(catalog, payload)
            if len(catalog) > before:
                props_events += 1
        if credits_used:
            invalidate_key_probe_cache()

    # Cap catalog size for the LLM while keeping props priority.
    props = [c for c in catalog if c.get("bet_type") == "player_prop"]
    games = [c for c in catalog if c.get("bet_type") != "player_prop"]
    # Prefer sooner games for game lines.
    games.sort(key=lambda c: hours_until_event(c.get("event_start")) or 9999)
    # Keep a playable mix for ranking.
    trimmed = props[:80] + games[:60]
    for i, row in enumerate(trimmed):
        row["id"] = f"fd{i+1}"

    return {
        "items": trimmed,
        "total": len(trimmed),
        "game_lines": len([c for c in trimmed if c["bet_type"] != "player_prop"]),
        "player_props": len([c for c in trimmed if c["bet_type"] == "player_prop"]),
        "credits_used": credits_used,
        "props_events": props_events,
        "cache_events": len(events),
        "message": None
        if trimmed
        else "No FanDuel lines in cache — tap Fetch live odds once, then run Atlas Insight.",
    }
