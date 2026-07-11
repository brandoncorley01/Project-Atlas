"""Atlas Insight search — OpenAI web search only (no Odds API)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.sports_analyst import PREFERRED_BOOK_KEY, US_PREFERRED_BOOK_KEYS
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_BOOK_TITLE_MAP = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "williamhill_us": "Caesars",
}

_SYSTEM = """You are Atlas sports bet search for Project Atlas.
The user is searching for real sportsbook markets (teams, games, or individual players/props).

HARD RULES:
- Use web search. Only return markets you can confirm are currently listed on real US sportsbooks.
- Prefer FanDuel and DraftKings. Include BetMGM/Caesars only if clearly listed.
- NEVER invent a player, team, line, or odds. If you cannot verify a market on a book, omit it.
- Support player props AND game lines (moneyline, spread, total).
- Prefer MLB and WNBA when relevant, but include other major US sports when they match the query.
- Odds may be approximate from public quotes; mark each book that lists the market.
- If the query is a player name, prioritize that player's props.
- If the query is a team, return that team's upcoming game lines and notable props.

Return JSON only:
{
  "markets": [
    {
      "sport": "MLB",
      "event_name": "Away @ Home",
      "home_team": "Home",
      "away_team": "Away",
      "event_start": "ISO8601 or null",
      "bet_type": "moneyline|spread|total|player_prop",
      "selection": "exact bet text e.g. Yankees -1.5 or Aaron Judge Over 1.5 Hits",
      "odds_american": -110,
      "point": null,
      "player_name": "Aaron Judge or null",
      "available_on": [
        {"book_key": "fanduel", "book_title": "FanDuel", "odds_american": -110},
        {"book_key": "draftkings", "book_title": "DraftKings", "odds_american": -115}
      ],
      "sources": ["site names you used"]
    }
  ],
  "summary": "one short sentence"
}
Return 6-16 markets max. Every market MUST include at least one available_on book."""


def _norm_book_key(raw: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "", (raw or "").lower())
    aliases = {
        "fd": "fanduel",
        "fanduel": "fanduel",
        "dk": "draftkings",
        "draftkings": "draftkings",
        "draftking": "draftkings",
        "betmgm": "betmgm",
        "mgm": "betmgm",
        "caesars": "caesars",
        "williamhill": "williamhill_us",
        "williamhillus": "williamhill_us",
    }
    return aliases.get(t, t or "market")


def _safe_american(value: Any, default: int = -110) -> int:
    try:
        n = int(value)
        if -10000 <= n <= 10000 and n != 0:
            return n
    except (TypeError, ValueError):
        pass
    return default


def _safe_point(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_available_on(raw: Any, fallback_odds: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = raw if isinstance(raw, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _norm_book_key(str(row.get("book_key") or row.get("book") or row.get("book_title") or ""))
        title = str(row.get("book_title") or _BOOK_TITLE_MAP.get(key) or key).strip() or key
        if not key or key in seen:
            continue
        seen.add(key)
        odds = row.get("odds_american")
        if odds is None:
            odds = fallback_odds
        out.append(
            {
                "book_key": key,
                "book_title": title,
                "odds_american": _safe_american(odds, fallback_odds),
            }
        )
    # Prefer US retail books first.
    out.sort(key=lambda b: 0 if b["book_key"] in US_PREFERRED_BOOK_KEYS else 1)
    return out


def _normalize_market(raw: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    selection = str(raw.get("selection") or "").strip()
    event_name = str(raw.get("event_name") or "").strip()
    if not selection:
        return None
    bet_type = str(raw.get("bet_type") or "moneyline").strip().lower()
    if bet_type not in {"moneyline", "spread", "total", "player_prop", "futures"}:
        bet_type = "player_prop" if raw.get("player_name") else "moneyline"
    odds = _safe_american(raw.get("odds_american"))
    available = _normalize_available_on(raw.get("available_on"), odds)
    if not available:
        # Require at least one named book — inventing "market" alone is not enough.
        return None
    # Prefer FanDuel display price when present.
    primary = available[0]
    for a in available:
        if a["book_key"] == PREFERRED_BOOK_KEY:
            primary = a
            break
    odds = _safe_american(primary.get("odds_american"), odds)
    home = str(raw.get("home_team") or "").strip()
    away = str(raw.get("away_team") or "").strip()
    if not event_name and home and away:
        event_name = f"{away} @ {home}"
    if not event_name:
        event_name = "Upcoming event"
    player = str(raw.get("player_name") or "").strip() or None
    sources = [str(s).strip() for s in (raw.get("sources") or []) if str(s).strip()][:6]
    event_id = f"openai-search-{index}"
    return {
        "event_id": event_id,
        "sport": str(raw.get("sport") or "Sports")[:40],
        "sport_key": str(raw.get("sport_key") or "") or None,
        "home_team": home,
        "away_team": away,
        "event_name": event_name[:160],
        "event_start": str(raw.get("event_start")).strip() if raw.get("event_start") else None,
        "hours_until_start": None,
        "bet_type": bet_type,
        "selection": selection[:140],
        "odds_american": odds,
        "point": _safe_point(raw.get("point")),
        "book_key": primary["book_key"],
        "book_title": primary["book_title"],
        "player_name": player,
        "prop_market": raw.get("prop_market"),
        "available_on": available,
        "available_books": [a["book_title"] for a in available],
        "fanduel_verified": any(a["book_key"] == PREFERRED_BOOK_KEY for a in available),
        "sources": sources,
        "openai_search": True,
    }


def _group_events(markets: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    by_event: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for m in markets:
        key = _norm_event_key(m)
        if key not in by_event:
            by_event[key] = {
                "event_id": m.get("event_id"),
                "sport": m.get("sport"),
                "sport_key": m.get("sport_key"),
                "home_team": m.get("home_team") or "",
                "away_team": m.get("away_team") or "",
                "event_name": m.get("event_name"),
                "event_start": m.get("event_start"),
                "hours_until_start": m.get("hours_until_start"),
                "markets": [],
            }
            order.append(key)
        if len(by_event[key]["markets"]) >= 18:
            continue
        by_event[key]["markets"].append(
            {
                "bet_type": m.get("bet_type"),
                "selection": m.get("selection"),
                "odds_american": m.get("odds_american"),
                "point": m.get("point"),
                "book_key": m.get("book_key"),
                "book_title": m.get("book_title"),
                "team_or_side": m.get("selection"),
                "player_name": m.get("player_name"),
                "available_on": m.get("available_on") or [],
                "available_books": m.get("available_books") or [],
            }
        )
    return [by_event[k] for k in order[: max(1, min(limit, 40))]]


def _norm_event_key(m: dict[str, Any]) -> str:
    name = re.sub(r"[^a-z0-9]+", " ", str(m.get("event_name") or "").lower()).strip()
    sport = re.sub(r"[^a-z0-9]+", " ", str(m.get("sport") or "").lower()).strip()
    return f"{sport}|{name}" or str(m.get("event_id") or "event")


async def search_markets_with_openai(
    *,
    query: str = "",
    sport: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Search teams/players via OpenAI web search — 0 Odds API credits."""
    q = (query or "").strip()
    if not q:
        return {
            "items": [],
            "markets": [],
            "total": 0,
            "markets_total": 0,
            "credits_used": 0,
            "cache": False,
            "openai_search": True,
            "message": "Type a team or player name, then press Search (powered by Atlas Insight / OpenAI).",
        }

    if not llm_service.is_configured():
        return {
            "items": [],
            "markets": [],
            "total": 0,
            "markets_total": 0,
            "credits_used": 0,
            "cache": False,
            "openai_search": False,
            "message": "OPENAI_API_KEY is not configured on the API — add it on Render/.env.",
        }

    sport_hint = f" Prefer sport filter: {sport}." if sport else ""
    user = (
        f"Search query: {q!r}.{sport_hint}\n"
        "Find currently listed FanDuel/DraftKings markets matching this query "
        "(player props and/or game lines). Include available_on for each book that lists it."
    )

    try:
        payload = await llm_service.complete_json_with_web_search(
            system=_SYSTEM,
            user=user,
            max_tokens=2200,
        )
    except Exception as exc:
        logger.warning("OpenAI sports search failed: %s", exc)
        payload = None

    if not payload:
        return {
            "items": [],
            "markets": [],
            "total": 0,
            "markets_total": 0,
            "credits_used": 0,
            "cache": False,
            "openai_search": True,
            "message": "Atlas Insight search returned nothing — try another team/player name.",
        }

    raw_markets = payload.get("markets") if isinstance(payload.get("markets"), list) else []
    markets: list[dict[str, Any]] = []
    for i, row in enumerate(raw_markets):
        normalized = _normalize_market(row, index=i + 1)
        if normalized:
            markets.append(normalized)
        if len(markets) >= max(1, min(limit, 24)):
            break

    items = _group_events(markets, limit=limit)
    web = bool(payload.get("_web_search"))
    summary = str(payload.get("summary") or "").strip()
    msg = summary or None
    if not markets:
        msg = (
            "No verified sportsbook markets found for that search. "
            "Try a clearer team or player name (e.g. Yankees, Judge, Aces)."
        )
    elif not web:
        msg = (msg + " " if msg else "") + "Web browse unavailable — results may be less current."

    return {
        "items": items,
        "markets": markets,
        "total": len(items),
        "markets_total": len(markets),
        "credits_used": 0,
        "cache": False,
        "openai_search": True,
        "web_search": web,
        "query": q,
        "sport": sport,
        "books": ["FanDuel", "DraftKings"],
        "message": msg,
    }
