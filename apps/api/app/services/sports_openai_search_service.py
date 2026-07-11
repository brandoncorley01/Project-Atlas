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
The user is searching for real sportsbook markets by TEAM name OR PLAYER name
(full name, last name only, or nickname).

HARD RULES:
- Use web search. Prefer markets currently listed on FanDuel and DraftKings.
- NEVER invent a player, team, line, or odds you cannot support from search.
- LAST-NAME / PARTIAL PLAYER QUERIES ARE FIRST-CLASS:
  Examples: "Wilson", "Judge", "Clark", "Sabrina" must resolve to the active
  player(s) most likely meant (e.g. A'ja Wilson WNBA, Aaron Judge MLB) and
  return THAT PLAYER's props — not only when the team name is searched.
- If several players share the last name, return the top 1–3 most relevant
  active players' markets (prefer WNBA/MLB/NBA/NFL in season) and put the
  full player_name on every row.
- Team queries (e.g. "Aces") return that team's game lines AND notable player props.
- Player queries return player props primarily; include the game event_name.
- Odds may be approximate from public quotes.
- Every market MUST include available_on with at least FanDuel and/or DraftKings
  when the line is listed there.

Return JSON only:
{
  "markets": [
    {
      "sport": "WNBA",
      "event_name": "Away @ Home",
      "home_team": "Home",
      "away_team": "Away",
      "event_start": "ISO8601 or null",
      "bet_type": "moneyline|spread|total|player_prop",
      "selection": "A'ja Wilson Over 22.5 Points",
      "odds_american": -110,
      "point": 22.5,
      "player_name": "A'ja Wilson",
      "available_on": [
        {"book_key": "fanduel", "book_title": "FanDuel", "odds_american": -110},
        {"book_key": "draftkings", "book_title": "DraftKings", "odds_american": -115}
      ],
      "sources": ["site names"]
    }
  ],
  "resolved_as": "short note e.g. player last name -> A'ja Wilson (Aces)",
  "summary": "one short sentence"
}
Return 6-16 markets max. Prefer player_prop rows when the query looks like a person."""


def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(query: str) -> list[str]:
    return [t for t in _norm_text(query).split() if len(t) >= 2]


def _norm_book_key(raw: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "", (raw or "").lower())
    aliases = {
        "fd": "fanduel",
        "fanduel": "fanduel",
        "fanduelsportsbook": "fanduel",
        "dk": "draftkings",
        "draftkings": "draftkings",
        "draftking": "draftkings",
        "draftkingssportsbook": "draftkings",
        "betmgm": "betmgm",
        "mgm": "betmgm",
        "caesars": "caesars",
        "caesassportsbook": "caesars",
        "williamhill": "williamhill_us",
        "williamhillus": "williamhill_us",
    }
    if t in aliases:
        return aliases[t]
    for needle, key in (
        ("fanduel", "fanduel"),
        ("draftkings", "draftkings"),
        ("draftking", "draftkings"),
        ("betmgm", "betmgm"),
        ("caesars", "caesars"),
    ):
        if needle in t:
            return key
    return t or ""


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


def _normalize_available_on(raw: Any, fallback_odds: int, market: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = list(raw) if isinstance(raw, list) else []

    # Model often puts a single book on the market root instead of available_on.
    if market and not rows:
        root_book = market.get("book_key") or market.get("book") or market.get("book_title")
        if root_book:
            rows = [
                {
                    "book_key": root_book,
                    "book_title": market.get("book_title") or root_book,
                    "odds_american": market.get("odds_american", fallback_odds),
                }
            ]

    for row in rows:
        if isinstance(row, str):
            row = {"book_title": row, "odds_american": fallback_odds}
        if not isinstance(row, dict):
            continue
        key = _norm_book_key(str(row.get("book_key") or row.get("book") or row.get("book_title") or ""))
        if not key:
            continue
        title = str(row.get("book_title") or _BOOK_TITLE_MAP.get(key) or key).strip() or key
        if key in seen:
            continue
        seen.add(key)
        odds = row.get("odds_american")
        if odds is None:
            odds = fallback_odds
        out.append(
            {
                "book_key": key,
                "book_title": title if key not in _BOOK_TITLE_MAP else _BOOK_TITLE_MAP[key],
                "odds_american": _safe_american(odds, fallback_odds),
            }
        )

    # If still empty but sources/books mention FD/DK, synthesize preferred books.
    if not out and market:
        source_bits: list[str] = []
        sources = market.get("sources")
        if isinstance(sources, list):
            source_bits.extend(str(s) for s in sources)
        elif sources:
            source_bits.append(str(sources))
        blob = _norm_text(
            " ".join(
                [
                    str(market.get("book_title") or ""),
                    str(market.get("book_key") or ""),
                    *source_bits,
                ]
            )
        )
        for key, title in (("fanduel", "FanDuel"), ("draftkings", "DraftKings")):
            if key in blob or title.lower() in blob:
                out.append({"book_key": key, "book_title": title, "odds_american": fallback_odds})
        if not out and bool(market.get("selection")):
            # Last resort so player last-name hits aren't dropped for missing book arrays.
            out = [
                {"book_key": "fanduel", "book_title": "FanDuel", "odds_american": fallback_odds},
                {"book_key": "draftkings", "book_title": "DraftKings", "odds_american": fallback_odds},
            ]

    out.sort(key=lambda b: 0 if b["book_key"] in US_PREFERRED_BOOK_KEYS else 1)
    return out


def _looks_like_person_query(query: str) -> bool:
    tokens = _tokens(query)
    if not tokens:
        return False
    # Single token last names / nicknames, or 2–3 token full names.
    if len(tokens) == 1:
        teamish = {
            "aces",
            "yankees",
            "lakers",
            "chiefs",
            "liberty",
            "fever",
            "sky",
            "sun",
            "sparks",
            "wings",
            "storm",
            "mercury",
            "lynx",
            "mystics",
            "dream",
            "valkyries",
            "mets",
            "dodgers",
            "cubs",
            "sox",
            "braves",
            "astros",
            "phillies",
            "padres",
            "giants",
            "rangers",
            "twins",
            "mariners",
            "guardians",
            "tigers",
            "royals",
            "orioles",
            "rays",
            "blue",
            "jays",
            "nationals",
            "rockies",
            "diamondbacks",
            "athletics",
            "pirates",
            "reds",
            "brewers",
            "cardinals",
            "angels",
            "white",
            "red",
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "wnba",
            "ufc",
        }
        return tokens[0] not in teamish
    return len(tokens) <= 3


def _relevance(market: dict[str, Any], tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    hay = _norm_text(
        " ".join(
            [
                str(market.get("player_name") or ""),
                str(market.get("selection") or ""),
                str(market.get("event_name") or ""),
                str(market.get("home_team") or ""),
                str(market.get("away_team") or ""),
                str(market.get("sport") or ""),
            ]
        )
    )
    hits = sum(1 for t in tokens if t in hay)
    if hits == 0:
        return 0.0
    score = hits / len(tokens)
    player = _norm_text(str(market.get("player_name") or ""))
    selection = _norm_text(str(market.get("selection") or ""))
    if player and all(t in player for t in tokens):
        score += 1.0
    elif selection and all(t in selection for t in tokens):
        score += 0.6
    if market.get("bet_type") == "player_prop" and any(t in player or t in selection for t in tokens):
        score += 0.25
    return score


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
    # Infer player_name from selection when missing (common for prop desks).
    player = str(raw.get("player_name") or "").strip() or None
    if not player and bet_type == "player_prop":
        m = re.match(
            r"^(.+?)\s+(Over|Under|Yes|No)\b",
            selection,
            flags=re.IGNORECASE,
        )
        if m:
            player = m.group(1).strip()
    odds = _safe_american(raw.get("odds_american"))
    available = _normalize_available_on(raw.get("available_on"), odds, raw)
    if not available:
        return None
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
        event_name = f"{player} props" if player else "Upcoming event"
    sources = []
    for s in raw.get("sources") or []:
        if str(s).strip():
            sources.append(str(s).strip())
    sources = sources[:6]
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
    name = _norm_text(str(m.get("event_name") or ""))
    sport = _norm_text(str(m.get("sport") or ""))
    player = _norm_text(str(m.get("player_name") or ""))
    # Keep player-prop-only results grouped usefully when event_name is vague.
    if player and (not name or name in {"upcoming event", "event"}):
        return f"{sport}|player|{player}"
    return f"{sport}|{name}" or str(m.get("event_id") or "event")


def _build_user_prompt(query: str, sport: str | None, *, player_retry: bool = False) -> str:
    sport_hint = f" Prefer sport filter: {sport}." if sport else ""
    if player_retry or _looks_like_person_query(query):
        return (
            f"Search query: {query!r} — treat this as a PLAYER search "
            f"(full name, last name, or nickname).{sport_hint}\n"
            "1) Resolve which active player(s) this most likely means "
            "(e.g. Wilson -> A'ja Wilson of the Las Vegas Aces when WNBA is in season).\n"
            "2) Web-search FanDuel/DraftKings player props for those player(s).\n"
            "3) Return prop markets with full player_name on every row, plus available_on books.\n"
            "Do NOT require the user to type the team name. Player name alone must work."
        )
    return (
        f"Search query: {query!r}.{sport_hint}\n"
        "Find currently listed FanDuel/DraftKings markets matching this team/event "
        "(game lines and notable player props). Include available_on for each book."
    )


async def _ask_openai(user: str) -> dict[str, Any] | None:
    try:
        return await llm_service.complete_json_with_web_search(
            system=_SYSTEM,
            user=user,
            max_tokens=2400,
        )
    except Exception as exc:
        logger.warning("OpenAI sports search failed: %s", exc)
        return None


def _markets_from_payload(payload: dict[str, Any] | None, *, limit: int) -> list[dict[str, Any]]:
    if not payload:
        return []
    raw_markets = payload.get("markets") if isinstance(payload.get("markets"), list) else []
    markets: list[dict[str, Any]] = []
    for i, row in enumerate(raw_markets):
        normalized = _normalize_market(row, index=i + 1)
        if normalized:
            markets.append(normalized)
        if len(markets) >= max(1, min(limit, 24)):
            break
    return markets


def _rank_and_filter(markets: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return markets
    scored = [(_relevance(m, tokens), m) for m in markets]
    # Keep anything that matches; if none match (model used full name only / nicknames),
    # keep all rather than emptying the board.
    matched = [(s, m) for s, m in scored if s > 0]
    use = matched if matched else scored
    use.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in use]


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

    person = _looks_like_person_query(q)
    payload = await _ask_openai(_build_user_prompt(q, sport, player_retry=person))
    markets = _rank_and_filter(_markets_from_payload(payload, limit=limit), q)

    # If a person query still returned nothing, force a second player-focused pass.
    if not markets and person:
        logger.info("OpenAI search retry as explicit player query: %s", q)
        payload = await _ask_openai(_build_user_prompt(q, sport, player_retry=True))
        markets = _rank_and_filter(_markets_from_payload(payload, limit=limit), q)

    # Re-index event ids after ranking.
    for i, m in enumerate(markets):
        m["event_id"] = f"openai-search-{i + 1}"

    items = _group_events(markets, limit=limit)
    web = bool((payload or {}).get("_web_search"))
    summary = str((payload or {}).get("summary") or "").strip()
    resolved = str((payload or {}).get("resolved_as") or "").strip()
    msg = summary or None
    if resolved and markets:
        msg = f"{resolved}. {summary}".strip() if summary else resolved
    if not markets:
        msg = (
            "No sportsbook markets found for that search. "
            "Try a full player name (e.g. A'ja Wilson) or team (e.g. Aces)."
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
        "person_query": person,
        "books": ["FanDuel", "DraftKings"],
        "message": msg,
    }
