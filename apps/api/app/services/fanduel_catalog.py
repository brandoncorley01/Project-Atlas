"""FanDuel-verified bet catalog for Atlas Insight — never invent markets."""

from __future__ import annotations

import logging
import re
from pathlib import Path
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

_PROPS_CACHE_PATH = Path(__file__).resolve().parents[2] / ".props_cache.json"
_PROPS_CACHE_TTL_MINUTES = 90
_BOOK_ORDER = ("fanduel", "draftkings", "betmgm", "williamhill_us")
US_SEARCH_BOOKS = "fanduel,draftkings"

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


def _read_props_cache_raw() -> dict[str, Any] | None:
    try:
        if not _PROPS_CACHE_PATH.exists():
            return None
        import json

        with _PROPS_CACHE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return None
        return data
    except (OSError, ValueError):
        return None


def _read_props_cache(*, respect_ttl: bool = True) -> dict[str, Any] | None:
    data = _read_props_cache_raw()
    if not data:
        return None
    if not respect_ttl:
        return data
    fetched_at = data.get("fetched_at")
    if fetched_at:
        from datetime import UTC, datetime

        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(str(fetched_at))).total_seconds() / 60
            if age > _PROPS_CACHE_TTL_MINUTES:
                return None
        except ValueError:
            pass
    return data


def _write_props_cache(items: list[dict[str, Any]], *, credits_used: int = 0) -> None:
    try:
        import json
        from datetime import UTC, datetime

        # Merge with existing props by selection+event+book (ignore TTL on merge).
        existing = _read_props_cache_raw()
        by_key: dict[str, dict[str, Any]] = {}
        for row in list((existing or {}).get("items") or []) + items:
            key = "|".join(
                [
                    str(row.get("event_id") or ""),
                    str(row.get("bet_type") or ""),
                    str(row.get("selection") or ""),
                    str(row.get("book_key") or ""),
                ]
            )
            by_key[key] = row
        payload = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "items": list(by_key.values()),
            "credits_used": credits_used,
        }
        with _PROPS_CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except (OSError, TypeError) as exc:
        logger.info("Props cache write failed: %s", exc)


def _market_identity(row: dict[str, Any]) -> str:
    """Identity for the same bet across books (ignore book-specific price)."""
    return "|".join(
        [
            str(row.get("event_id") or row.get("event_name") or ""),
            str(row.get("bet_type") or ""),
            _norm(str(row.get("selection") or "")),
            str(row.get("prop_market") or ""),
            str(row.get("point") if row.get("point") is not None else ""),
        ]
    )


def collapse_available_on(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge same market across books into one row with available_on[]."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        key = _market_identity(row)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    out: list[dict[str, Any]] = []
    for key in order:
        books = groups[key]
        books.sort(
            key=lambda r: _BOOK_ORDER.index(str(r.get("book_key")))
            if str(r.get("book_key")) in _BOOK_ORDER
            else 99
        )
        primary = dict(books[0])
        available = []
        seen_books: set[str] = set()
        for b in books:
            bk = str(b.get("book_key") or "")
            if not bk or bk in seen_books:
                continue
            seen_books.add(bk)
            available.append(
                {
                    "book_key": bk,
                    "book_title": b.get("book_title") or bk,
                    "odds_american": b.get("odds_american"),
                }
            )
        primary["available_on"] = available
        primary["available_books"] = [a["book_title"] for a in available]
        primary["fanduel_verified"] = any(a["book_key"] == PREFERRED_BOOK_KEY for a in available) or any(
            a["book_key"] in US_PREFERRED_BOOK_KEYS for a in available
        )
        # Prefer FanDuel odds as the display/playable number when present.
        for a in available:
            if a["book_key"] == PREFERRED_BOOK_KEY and a.get("odds_american") is not None:
                primary["odds_american"] = a["odds_american"]
                primary["book_key"] = PREFERRED_BOOK_KEY
                primary["book_title"] = "FanDuel"
                break
        out.append(primary)
    return out


def _append_game_lines(
    catalog: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    all_preferred_books: bool = False,
) -> None:
    """Append game lines. Insight uses FanDuel-first; search uses all preferred books."""
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    if not home or not away:
        return
    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    sport_key = str(event.get("_sport_key") or event.get("sport_key") or "")
    event_id = str(event.get("id") or "")
    event_name = f"{away} @ {home}"
    start = event.get("commence_time")

    books = _fanduel_books(event)
    if not all_preferred_books:
        # FanDuel preferred for Insight verification; fall back to first US book.
        fd = [b for b in books if str(b.get("key")) == PREFERRED_BOOK_KEY]
        books = (fd or books)[:1]
    else:
        books = [b for b in books if str(b.get("key") or "") in US_PREFERRED_BOOK_KEYS]

    for book in books:
        book_key = str(book.get("key") or PREFERRED_BOOK_KEY)
        if all_preferred_books and book_key not in US_PREFERRED_BOOK_KEYS:
            continue
        book_title = str(book.get("title") or book_key)
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
                        "fanduel_verified": book_key in US_PREFERRED_BOOK_KEYS,
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


def _append_prop_markets(
    catalog: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    preferred_only: bool = True,
) -> None:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    sport_key = str(event.get("_sport_key") or event.get("sport_key") or "")
    event_id = str(event.get("id") or "")
    event_name = f"{away} @ {home}" if home and away else str(event.get("event_name") or "Event")
    start = event.get("commence_time")

    books = _fanduel_books(event)
    if preferred_only:
        books = [b for b in books if str(b.get("key") or "") in US_PREFERRED_BOOK_KEYS] or books

    for book in books:
        book_key = str(book.get("key") or "")
        if preferred_only and book_key and book_key not in US_PREFERRED_BOOK_KEYS:
            continue
        book_key = book_key or PREFERRED_BOOK_KEY
        book_title = str(book.get("title") or book_key)
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
                        "fanduel_verified": book_key in US_PREFERRED_BOOK_KEYS,
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
                "bookmakers": US_SEARCH_BOOKS,
            },
        )
        return data if isinstance(data, dict) else None
    except OddsApiError as exc:
        logger.info("Verified props skip %s/%s: %s", sport_key, event_id[:8], exc)
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
            _append_prop_markets(catalog, payload, preferred_only=True)
            if len(catalog) > before:
                props_events += 1
                # Persist verified props so search can find players without re-spend.
                new_props = [c for c in catalog[before:] if c.get("bet_type") == "player_prop"]
                if new_props:
                    _write_props_cache(new_props, credits_used=cost)
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


def _market_haystack(row: dict[str, Any]) -> str:
    return _norm(
        " ".join(
            [
                str(row.get("player_name") or ""),
                str(row.get("selection") or ""),
                str(row.get("event_name") or ""),
                str(row.get("home_team") or ""),
                str(row.get("away_team") or ""),
                str(row.get("sport") or ""),
                str(row.get("bet_type") or ""),
                str(row.get("prop_market") or ""),
                " ".join(str(b) for b in (row.get("available_books") or [])),
            ]
        )
    )


def _tokens(query: str) -> list[str]:
    return [t for t in _norm(query).split() if len(t) >= 2]


def _match_score(haystack: str, tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in haystack)
    if hits == 0:
        return 0.0
    score = hits / len(tokens)
    if hits == len(tokens):
        score += 0.25
    # Strong boost when player name alone matches.
    return score


def build_verified_search_catalog() -> list[dict[str, Any]]:
    """Game lines (all FD/DK) + cached player props, collapsed with available_on."""
    cache = _read_cache()
    events = filter_upcoming_events(list(cache.get("events") or [])) if cache else []
    events = [e for e in events if not e.get("_is_outright")]

    raw: list[dict[str, Any]] = []
    for event in events:
        _append_game_lines(raw, event, all_preferred_books=True)

    props_cache = _read_props_cache(respect_ttl=False) or {}
    for row in props_cache.get("items") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("book_key") or "") not in US_PREFERRED_BOOK_KEYS:
            continue
        raw.append(dict(row))

    return collapse_available_on(raw)


def search_verified_markets(
    *,
    query: str = "",
    sport: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Search verified FanDuel/DraftKings markets — teams, events, and players."""
    from app.providers.sports.odds_api import _cache_age_minutes

    catalog = build_verified_search_catalog()
    if not catalog:
        return {
            "items": [],
            "markets": [],
            "total": 0,
            "markets_total": 0,
            "credits_used": 0,
            "cache": False,
            "message": (
                "No verified book lines yet — tap Fetch live odds once. "
                "For player props, run Atlas Insight after Fetch (props are cached from real books)."
            ),
        }

    sport_norm = _norm(sport or "")
    if sport_norm:
        catalog = [
            c
            for c in catalog
            if sport_norm in _norm(str(c.get("sport") or ""))
            or sport_norm in _norm(str(c.get("sport_key") or ""))
        ]

    tokens = _tokens(query)
    scored_markets: list[tuple[float, dict[str, Any]]] = []
    for row in catalog:
        # Only surface markets that exist on at least one real preferred book.
        books = row.get("available_on") or []
        if not books:
            continue
        if not any(str(b.get("book_key")) in US_PREFERRED_BOOK_KEYS for b in books):
            continue
        hay = _market_haystack(row)
        if tokens:
            score = _match_score(hay, tokens)
            if score <= 0:
                continue
            player = _norm(str(row.get("player_name") or ""))
            if player and all(t in player for t in tokens):
                score += 0.5
        else:
            # Browse mode: soon game lines only (props need an explicit player/team query).
            if row.get("bet_type") == "player_prop":
                continue
            score = 0.5
        hours = hours_until_event(row.get("event_start")) or 9999
        rank = score * 100 - min(hours, 200) * 0.05
        if tokens and row.get("bet_type") == "player_prop":
            rank += 5
        scored_markets.append((rank, row))

    scored_markets.sort(key=lambda x: x[0], reverse=True)
    market_cap = max(1, min(limit, 80))
    # Flat market hits are most useful when the user typed a query (esp. players).
    markets = []
    if tokens:
        for _, row in scored_markets[:market_cap]:
            markets.append(
                {
                    "event_id": row.get("event_id"),
                    "sport": row.get("sport"),
                    "sport_key": row.get("sport_key"),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "event_name": row.get("event_name"),
                    "event_start": row.get("event_start"),
                    "hours_until_start": (
                        round(h, 1)
                        if (h := hours_until_event(row.get("event_start"))) is not None
                        else None
                    ),
                    "bet_type": row.get("bet_type"),
                    "selection": row.get("selection"),
                    "odds_american": row.get("odds_american"),
                    "point": row.get("point"),
                    "book_key": row.get("book_key"),
                    "book_title": row.get("book_title"),
                    "player_name": row.get("player_name"),
                    "prop_market": row.get("prop_market"),
                    "available_on": row.get("available_on") or [],
                    "available_books": row.get("available_books") or [],
                    "fanduel_verified": bool(row.get("fanduel_verified")),
                }
            )

    # Group into events for the classic event picker (game lines + matched props).
    by_event: dict[str, dict[str, Any]] = {}
    event_rank: dict[str, float] = {}
    for rank, row in scored_markets:
        eid = str(row.get("event_id") or row.get("event_name") or "")
        if not eid:
            continue
        if eid not in by_event:
            hours = hours_until_event(row.get("event_start"))
            by_event[eid] = {
                "event_id": row.get("event_id"),
                "sport": row.get("sport"),
                "sport_key": row.get("sport_key"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "event_name": row.get("event_name"),
                "event_start": row.get("event_start"),
                "hours_until_start": round(hours, 1) if hours is not None else None,
                "markets": [],
            }
            event_rank[eid] = rank
        else:
            event_rank[eid] = max(event_rank[eid], rank)
        if len(by_event[eid]["markets"]) >= 24:
            continue
        by_event[eid]["markets"].append(
            {
                "bet_type": row.get("bet_type"),
                "selection": row.get("selection"),
                "odds_american": row.get("odds_american"),
                "point": row.get("point"),
                "book_key": row.get("book_key"),
                "book_title": row.get("book_title"),
                "team_or_side": row.get("selection"),
                "player_name": row.get("player_name"),
                "available_on": row.get("available_on") or [],
                "available_books": row.get("available_books") or [],
            }
        )

    ordered_events = sorted(by_event.keys(), key=lambda k: event_rank.get(k, 0), reverse=True)
    items = [by_event[k] for k in ordered_events[: max(1, min(limit, 80))]]

    odds_cache = _read_cache()
    age = _cache_age_minutes(odds_cache.get("fetched_at")) if odds_cache else None
    msg = None
    if tokens and not markets and not items:
        msg = (
            "No verified FanDuel/DraftKings markets matched. "
            "Try a team name, or run Atlas Insight after Fetch to cache player props."
        )
    elif tokens and markets and not any(m.get("player_name") for m in markets):
        msg = (
            "Showing verified game lines on FanDuel/DraftKings. "
            "Player props appear after Atlas Insight caches them from those books."
        )

    return {
        "items": items,
        "markets": markets,
        "total": len(items),
        "markets_total": len(markets),
        "credits_used": 0,
        "cache": True,
        "cache_age_minutes": round(age, 1) if age is not None else None,
        "query": query,
        "sport": sport,
        "message": msg,
        "books": ["FanDuel", "DraftKings"],
    }
