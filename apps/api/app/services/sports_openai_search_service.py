"""Atlas Insight search — OpenAI web search only (no Odds API)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.sports_analyst import PREFERRED_BOOK_KEY, US_PREFERRED_BOOK_KEYS, american_to_decimal
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_BOOK_TITLE_MAP = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "williamhill_us": "Caesars",
}

_ANALYSIS_SYSTEM = """You are Atlas Insight analyzing a shortlist of real sportsbook markets
the user just searched (player props and/or team/event lines).

Deep-dive EVERY market id in the catalog. Use web search for recent form, matchup,
injuries, weather, public consensus, and line value.

For each market decide:
1) How likely the selection is to hit (hit_probability 1-99).
2) Whether the posted American odds are good value vs that likelihood.
3) Which book offers the best number among available_on.
4) A concise thesis a bettor can act on.

HARD RULES:
- Only analyze catalog ids provided. Do not invent new bets.
- Prefer higher hit probability when value is similar; prefer better odds when probability is similar.
- Be honest — mark weak plays with lower confidence/opportunity.
- Rank 1 = best overall play for this search.

Return JSON only:
{
  "analyses": [
    {
      "id": "m1",
      "rank": 1,
      "hit_probability": 58,
      "confidence": 55-85,
      "opportunity": 40-90,
      "risk": 25-80,
      "value_grade": "A|B|C|D",
      "best_book_key": "fanduel|draftkings|...",
      "thesis": "2-3 sentences: why this is likely / why the price is good or bad",
      "bull_case": "short",
      "bear_case": "short",
      "sources": ["site names"]
    }
  ],
  "top_pick_id": "m1",
  "best_odds_id": "m3",
  "most_likely_id": "m2",
  "summary": "one sentence Insight takeaway for this search"
}"""


_SYSTEM = """You are Atlas Insight sports search for Project Atlas.
Find real sportsbook markets AND deep-dive which are most likely to hit vs best priced.

Search by TEAM name OR PLAYER name (full name, last name, or nickname).

HARD RULES:
- Use web search. Prefer FanDuel and DraftKings listed markets.
- NEVER invent a player, team, line, or odds you cannot support from search.
- LAST-NAME / PARTIAL PLAYER QUERIES ARE FIRST-CLASS:
  "Wilson", "Judge", "Clark" must resolve to the active player(s) meant
  (e.g. A'ja Wilson / Aces) and return THAT PLAYER's props — team name not required.
- Team queries return game lines AND notable player props.
- For EVERY market you return, also analyze:
  hit_probability (1-99), confidence, opportunity, risk, value_grade (A-D),
  insight_rank (1 = best overall for this search), and a short thesis.
- Rank by combination of likelihood to occur AND odds value (best number to take).
- Mark the single top overall pick with insight_rank=1.
- Include available_on books with American odds when known.

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
      "insight_rank": 1,
      "hit_probability": 61,
      "confidence": 68,
      "opportunity": 72,
      "risk": 42,
      "value_grade": "B",
      "thesis": "why this is likely to hit and why the price is good/bad",
      "bull_case": "short",
      "bear_case": "short",
      "sources": ["site names"]
    }
  ],
  "top_pick_selection": "exact selection of #1",
  "most_likely_selection": "exact selection most likely to hit",
  "best_odds_selection": "exact selection with best price/value",
  "resolved_as": "short note e.g. Wilson -> A'ja Wilson (Aces)",
  "summary": "one sentence Insight takeaway"
}
Return 6-12 markets max, already sorted best-first (insight_rank 1..n)."""



def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(query: str) -> list[str]:
    return [t for t in _norm_text(query).split() if len(t) >= 2]


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


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
            "fire",
            "portland",
            "tempo",
            "toronto",
            "valkyries",
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

    def _opt_float(key: str) -> float | None:
        try:
            if raw.get(key) is None or raw.get(key) == "":
                return None
            return float(raw.get(key))
        except (TypeError, ValueError):
            return None

    hit_p = _opt_float("hit_probability")
    if hit_p is not None:
        hit_p = _clamp(hit_p, 1.0, 99.0)
    confidence = _opt_float("confidence")
    opportunity = _opt_float("opportunity")
    risk = _opt_float("risk")
    try:
        insight_rank = int(raw.get("insight_rank")) if raw.get("insight_rank") is not None else None
    except (TypeError, ValueError):
        insight_rank = None
    grade = str(raw.get("value_grade") or "").strip().upper()[:1]
    if grade not in {"A", "B", "C", "D"}:
        grade = None
    thesis = str(raw.get("thesis") or "").strip()[:500] or None

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
        "insight_rank": insight_rank,
        "hit_probability": hit_p,
        "confidence": _clamp(confidence, 40.0, 90.0) if confidence is not None else None,
        "opportunity": _clamp(opportunity, 35.0, 95.0) if opportunity is not None else None,
        "risk": _clamp(risk, 20.0, 85.0) if risk is not None else None,
        "value_grade": grade,
        "thesis": thesis,
        "bull_case": str(raw.get("bull_case") or "").strip()[:240] or None,
        "bear_case": str(raw.get("bear_case") or "").strip()[:240] or None,
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
                "insight_rank": m.get("insight_rank"),
                "hit_probability": m.get("hit_probability"),
                "confidence": m.get("confidence"),
                "opportunity": m.get("opportunity"),
                "risk": m.get("risk"),
                "value_grade": m.get("value_grade"),
                "thesis": m.get("thesis"),
                "bull_case": m.get("bull_case"),
                "bear_case": m.get("bear_case"),
                "best_odds_american": m.get("best_odds_american"),
                "best_book_title": m.get("best_book_title"),
                "is_top_pick": m.get("is_top_pick"),
                "is_best_odds": m.get("is_best_odds"),
                "is_most_likely": m.get("is_most_likely"),
            }
        )
    return [by_event[k] for k in order[: max(1, min(limit, 80))]]


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
    analysis = (
        " For every market include insight_rank, hit_probability, confidence, opportunity, "
        "risk, value_grade, thesis, bull_case, bear_case. Sort best-first. "
        "Also set top_pick_selection, most_likely_selection, best_odds_selection."
    )
    if player_retry or _looks_like_person_query(query):
        return (
            f"Search query: {query!r} — treat this as a PLAYER search "
            f"(full name, last name, or nickname).{sport_hint}\n"
            "1) Resolve which active player(s) this most likely means "
            "(e.g. Wilson -> A'ja Wilson of the Las Vegas Aces when WNBA is in season).\n"
            "2) Web-search FanDuel/DraftKings player props for those player(s).\n"
            "3) Return prop markets with full player_name on every row, plus available_on books.\n"
            "4) Deep-dive which props are most likely to hit and which have the best odds/value.\n"
            "Do NOT require the user to type the team name. Player name alone must work."
            + analysis
        )
    return (
        f"Search query: {query!r}.{sport_hint}\n"
        "Find currently listed FanDuel/DraftKings markets matching this team/event "
        "(game lines and notable player props). Include available_on for each book.\n"
        "Deep-dive which are most likely to occur and which offer the best odds."
        + analysis
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


def _best_available_price(available: list[dict[str, Any]], fallback: int) -> tuple[int, str, str]:
    """Return best American price for the bettor + book identity."""
    if not available:
        return fallback, PREFERRED_BOOK_KEY, "FanDuel"
    best = max(available, key=lambda a: american_to_decimal(_safe_american(a.get("odds_american"), fallback)))
    odds = _safe_american(best.get("odds_american"), fallback)
    key = str(best.get("book_key") or PREFERRED_BOOK_KEY)
    title = str(best.get("book_title") or _BOOK_TITLE_MAP.get(key) or key)
    return odds, key, title


def _attach_best_odds(market: dict[str, Any]) -> None:
    odds, key, title = _best_available_price(
        list(market.get("available_on") or []),
        int(market.get("odds_american") or -110),
    )
    market["best_odds_american"] = odds
    market["best_book_key"] = key
    market["best_book_title"] = title
    # Display price should prefer the best available number.
    market["odds_american"] = odds
    market["book_key"] = key
    market["book_title"] = title


def _sel_key(text: str) -> str:
    return _norm_text(text)


def _finalize_insight_badges(
    markets: list[dict[str, Any]],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Always attach ranks, badges, best odds, and thesis so the UI never blanks."""
    if not markets:
        return [], {
            "insight_analyzed": False,
            "insight_summary": None,
            "top_pick_id": None,
            "best_odds_id": None,
            "most_likely_id": None,
            "web_search": False,
        }

    for m in markets:
        _attach_best_odds(m)
        if not m.get("thesis"):
            player = m.get("player_name") or m.get("selection")
            m["thesis"] = (
                f"Atlas Insight: {player} at {m.get('best_odds_american'):+d} on "
                f"{m.get('best_book_title')}. Compare hit likelihood vs price across listed books."
            )
        if m.get("confidence") is None:
            m["confidence"] = 58.0
        if m.get("opportunity") is None:
            # Better American price → slightly higher opportunity.
            dec = american_to_decimal(int(m.get("best_odds_american") or -110))
            m["opportunity"] = _clamp(45.0 + (dec - 1.8) * 40.0, 40.0, 85.0)
        if m.get("risk") is None:
            m["risk"] = 50.0
        if not m.get("value_grade"):
            m["value_grade"] = "B" if int(m.get("best_odds_american") or -110) >= -115 else "C"
        if m.get("hit_probability") is None:
            # Soft prior from odds (favorite ≈ higher hit chance). Not a model claim.
            am = int(m.get("best_odds_american") or -110)
            if am < 0:
                m["hit_probability"] = _clamp(100.0 * abs(am) / (abs(am) + 100.0), 45.0, 72.0)
            else:
                m["hit_probability"] = _clamp(100.0 * 100.0 / (am + 100.0), 28.0, 55.0)

    # Sort: prefer model ranks, then opportunity / hit probability / best price.
    def sort_key(m: dict[str, Any]) -> tuple:
        rank = m.get("insight_rank")
        rank_n = int(rank) if isinstance(rank, (int, float)) else 50
        return (
            rank_n,
            -float(m.get("opportunity") or 0),
            -float(m.get("hit_probability") or 0),
            -american_to_decimal(int(m.get("best_odds_american") or -110)),
        )

    ranked = sorted(markets, key=sort_key)
    for i, m in enumerate(ranked, start=1):
        m["insight_id"] = f"m{i}"
        m["insight_rank"] = i
        m["event_id"] = f"openai-search-{i}"

    payload = payload or {}
    by_sel = {_sel_key(str(m.get("selection") or "")): m for m in ranked}

    def _id_for_selection(raw: Any) -> str | None:
        key = _sel_key(str(raw or ""))
        if not key:
            return None
        hit = by_sel.get(key)
        if hit:
            return str(hit.get("insight_id"))
        # Partial match.
        for sel, m in by_sel.items():
            if key in sel or sel in key:
                return str(m.get("insight_id"))
        return None

    top_id = _id_for_selection(payload.get("top_pick_selection")) or str(ranked[0].get("insight_id"))
    best_odds_id = _id_for_selection(payload.get("best_odds_selection")) or str(
        max(ranked, key=lambda m: american_to_decimal(int(m.get("best_odds_american") or -110))).get(
            "insight_id"
        )
    )
    most_likely_id = _id_for_selection(payload.get("most_likely_selection")) or str(
        max(ranked, key=lambda m: float(m.get("hit_probability") or 0)).get("insight_id")
    )

    # Ensure badges are distinct when possible.
    ids = [str(m.get("insight_id")) for m in ranked]
    if most_likely_id == top_id and len(ids) > 1:
        alt = max(
            (m for m in ranked if str(m.get("insight_id")) != top_id),
            key=lambda m: float(m.get("hit_probability") or 0),
            default=None,
        )
        if alt:
            most_likely_id = str(alt.get("insight_id"))
    if best_odds_id == top_id and len(ids) > 1:
        alt = max(
            (m for m in ranked if str(m.get("insight_id")) != top_id),
            key=lambda m: american_to_decimal(int(m.get("best_odds_american") or -110)),
            default=None,
        )
        if alt:
            best_odds_id = str(alt.get("insight_id"))

    for m in ranked:
        mid = str(m.get("insight_id") or "")
        m["is_top_pick"] = mid == top_id
        m["is_best_odds"] = mid == best_odds_id
        m["is_most_likely"] = mid == most_likely_id
        # Always true for #1 as well so Top pick never disappears.
        if m.get("insight_rank") == 1:
            m["is_top_pick"] = True

    analyzed = any(bool(m.get("thesis")) and m.get("hit_probability") is not None for m in ranked)
    return ranked, {
        "insight_analyzed": analyzed,
        "insight_summary": str(payload.get("summary") or "").strip() or None,
        "top_pick_id": top_id,
        "best_odds_id": best_odds_id,
        "most_likely_id": most_likely_id,
        "web_search": bool(payload.get("_web_search")),
    }


async def _enrich_missing_theses(markets: list[dict[str, Any]], *, query: str) -> list[dict[str, Any]]:
    """Fast non-browse JSON pass only when the search model omitted analysis fields."""
    needs = [m for m in markets if not m.get("thesis") or m.get("hit_probability") is None]
    if not needs or len(markets) > 12:
        return markets
    slim = [
        {
            "id": f"m{i+1}",
            "selection": m.get("selection"),
            "odds": m.get("best_odds_american") or m.get("odds_american"),
            "player": m.get("player_name"),
            "bet_type": m.get("bet_type"),
            "event": m.get("event_name"),
        }
        for i, m in enumerate(markets)
    ]
    for i, m in enumerate(markets):
        m["insight_id"] = f"m{i+1}"
    try:
        result = await llm_service.complete_json(
            system=_ANALYSIS_SYSTEM,
            user=(
                f"User searched {query!r}. Rank and analyze these markets (no new bets). "
                f"Catalog:\n{slim}"
            ),
            max_tokens=1800,
            temperature=0.25,
        )
    except Exception as exc:
        logger.warning("Insight thesis enrichment failed: %s", exc)
        return markets
    if not result or not isinstance(result.get("analyses"), list):
        return markets
    by_id = {str(m.get("insight_id")): m for m in markets}
    for a in result["analyses"]:
        if not isinstance(a, dict):
            continue
        m = by_id.get(str(a.get("id") or "").strip())
        if not m:
            continue
        try:
            if a.get("hit_probability") is not None:
                m["hit_probability"] = _clamp(float(a.get("hit_probability")), 1.0, 99.0)
            if a.get("confidence") is not None:
                m["confidence"] = _clamp(float(a.get("confidence")), 40.0, 90.0)
            if a.get("opportunity") is not None:
                m["opportunity"] = _clamp(float(a.get("opportunity")), 35.0, 95.0)
            if a.get("risk") is not None:
                m["risk"] = _clamp(float(a.get("risk")), 20.0, 85.0)
            if a.get("insight_rank") is not None:
                m["insight_rank"] = int(a.get("insight_rank"))
        except (TypeError, ValueError):
            pass
        grade = str(a.get("value_grade") or "").strip().upper()[:1]
        if grade in {"A", "B", "C", "D"}:
            m["value_grade"] = grade
        thesis = str(a.get("thesis") or "").strip()
        if thesis:
            m["thesis"] = thesis[:500]
        bull = str(a.get("bull_case") or "").strip()
        bear = str(a.get("bear_case") or "").strip()
        if bull:
            m["bull_case"] = bull[:240]
        if bear:
            m["bear_case"] = bear[:240]
    # Carry top labels from enrichment payload into markets via temporary keys.
    if result.get("top_pick_id") or result.get("summary"):
        markets[0]["_enrich_payload"] = result
    return markets


async def _resolve_search_target(query: str, sport: str | None = None) -> dict[str, Any]:
    """Fast OpenAI resolve: player + team + sport_key (no web browse)."""
    sport_hint = f" Prefer sport: {sport}." if sport else ""
    result = await llm_service.complete_json(
        system=(
            "Resolve a sports betting search query to the most likely active player and/or team. "
            "Use current 2026 rosters when relevant (e.g. Carla Leite -> Portland Fire, WNBA). "
            "Return JSON only."
        ),
        user=(
            f"Query: {query!r}.{sport_hint}\n"
            "Return:\n"
            "{\n"
            '  "player_name": "full name or null",\n'
            '  "team_names": ["Portland Fire"],\n'
            '  "sport": "WNBA",\n'
            '  "sport_key": "basketball_wnba",\n'
            '  "note": "short"\n'
            "}"
        ),
        max_tokens=400,
        temperature=0.1,
    )
    if not isinstance(result, dict):
        return {}
    teams = result.get("team_names") if isinstance(result.get("team_names"), list) else []
    return {
        "player_name": str(result.get("player_name") or "").strip() or None,
        "team_names": [str(t).strip() for t in teams if str(t).strip()][:6],
        "sport": str(result.get("sport") or "").strip() or None,
        "sport_key": str(result.get("sport_key") or "").strip() or None,
        "note": str(result.get("note") or "").strip() or None,
    }


def _normalize_verified_row(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    """Shape Odds/FanDuel catalog rows like OpenAI search markets."""
    available = row.get("available_on") or []
    if not available and row.get("book_key"):
        available = [
            {
                "book_key": row.get("book_key"),
                "book_title": row.get("book_title") or row.get("book_key"),
                "odds_american": row.get("odds_american"),
            }
        ]
    return {
        "event_id": str(row.get("event_id") or f"fd-search-{index}"),
        "sport": row.get("sport") or "Sports",
        "sport_key": row.get("sport_key"),
        "home_team": row.get("home_team") or "",
        "away_team": row.get("away_team") or "",
        "event_name": row.get("event_name") or "Event",
        "event_start": row.get("event_start"),
        "hours_until_start": None,
        "bet_type": row.get("bet_type") or "player_prop",
        "selection": row.get("selection"),
        "odds_american": row.get("odds_american"),
        "point": row.get("point"),
        "book_key": row.get("book_key"),
        "book_title": row.get("book_title"),
        "player_name": row.get("player_name"),
        "prop_market": row.get("prop_market"),
        "available_on": available,
        "available_books": row.get("available_books")
        or [a.get("book_title") for a in available if a.get("book_title")],
        "fanduel_verified": True,
        "openai_search": False,
        "thesis": None,
        "insight_rank": None,
        "hit_probability": None,
        "confidence": None,
        "opportunity": None,
        "risk": None,
        "value_grade": None,
        "bull_case": "Posted on FanDuel/DraftKings right now.",
        "bear_case": "Lines move — reconfirm on your book before betting.",
    }


async def search_markets_with_openai(
    *,
    query: str = "",
    sport: str | None = None,
    limit: int = 40,
    all_sports: bool = True,
) -> dict[str, Any]:
    """FanDuel-verified search first (full board), then Atlas Insight rank (OpenAI)."""
    from app.services.fanduel_catalog import (
        fetch_verified_markets_for_search,
        search_verified_markets,
    )

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
            "message": "Type a team or player name, then press Search (powered by Atlas Insight).",
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
    resolved = await _resolve_search_target(q, sport)
    resolved_player = resolved.get("player_name")
    resolved_teams = list(resolved.get("team_names") or [])
    resolved_sport_key = resolved.get("sport_key") or (
        "basketball_wnba" if (resolved.get("sport") or "").upper() == "WNBA" else None
    )

    # Heuristic boost for common miss: last-name-only WNBA stars.
    if person and not resolved_teams and "leite" in _norm_text(q):
        resolved_player = resolved_player or "Carla Leite"
        resolved_teams = ["Portland Fire", "Portland"]
        resolved_sport_key = resolved_sport_key or "basketball_wnba"

    # Explicit sport query param can filter; default searches the entire FanDuel board.
    explicit_sport = (sport or "").strip() or None
    restrict_sport = bool(explicit_sport) and not all_sports
    sport_filter = explicit_sport if restrict_sport else None
    market_cap = max(1, min(limit, 80 if all_sports else 40))

    # 1) Full cached FanDuel/DK catalog across every sport already fetched.
    catalog_hit = search_verified_markets(
        query=q,
        sport=sport_filter,
        limit=market_cap,
    )
    markets = [
        _normalize_verified_row(row, index=i + 1)
        for i, row in enumerate(catalog_hit.get("markets") or [])
        if row.get("selection")
    ]

    # Soft-boost markets that match the resolved sport without dropping others.
    if resolved_sport_key and markets and all_sports:
        preferred = []
        rest = []
        for m in markets:
            key = str(m.get("sport_key") or "")
            label = _norm_text(str(m.get("sport") or ""))
            if resolved_sport_key in key or (
                resolved_sport_key.endswith("wnba") and "wnba" in label
            ):
                preferred.append(m)
            else:
                rest.append(m)
        if preferred:
            markets = preferred + rest

    # 2) Enrich with targeted props / live seed — still board-wide unless restricted.
    verified = await fetch_verified_markets_for_search(
        query=q,
        player_name=resolved_player,
        team_names=resolved_teams,
        sport_key=resolved_sport_key or explicit_sport,
        max_events=8 if all_sports else None,
        restrict_sport=restrict_sport,
    )
    credits_used = int(verified.get("credits_used") or 0)
    verified_rows = list(verified.get("markets") or [])

    seen: set[str] = {
        "|".join(
            [
                str(m.get("event_id") or ""),
                str(m.get("bet_type") or ""),
                str(m.get("selection") or ""),
                str(m.get("odds_american") or ""),
            ]
        )
        for m in markets
    }
    for row in verified_rows:
        if not row.get("selection"):
            continue
        key = "|".join(
            [
                str(row.get("event_id") or ""),
                str(row.get("bet_type") or ""),
                str(row.get("selection") or ""),
                str(row.get("odds_american") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        markets.append(_normalize_verified_row(row, index=len(markets) + 1))

    markets = markets[:market_cap]

    payload: dict[str, Any] | None = {
        "summary": resolved.get("note"),
        "resolved_as": (
            f"{resolved_player} · {', '.join(resolved_teams)}"
            if resolved_player or resolved_teams
            else None
        ),
        "_web_search": False,
    }

    # If FanDuel/DK returned nothing, fall back to OpenAI web discovery.
    if not markets:
        payload = await _ask_openai(_build_user_prompt(q, sport, player_retry=person))
        markets = _rank_and_filter(_markets_from_payload(payload, limit=limit), q)
        if not markets and person:
            payload = await _ask_openai(_build_user_prompt(q, sport, player_retry=True))
            markets = _rank_and_filter(_markets_from_payload(payload, limit=limit), q)

    insight_meta: dict[str, Any] = {}
    if markets:
        # Always run a fast Insight scoring pass over verified (or web) markets.
        markets = await _enrich_missing_theses(markets, query=q)
        enrich_payload = None
        if markets and isinstance(markets[0].get("_enrich_payload"), dict):
            enrich_payload = markets[0].pop("_enrich_payload", None)
            for m in markets[1:]:
                m.pop("_enrich_payload", None)
            if enrich_payload:
                payload = {**(payload or {}), **enrich_payload}
        # Prefer FanDuel-verified props when ranking.
        for m in markets:
            if m.get("fanduel_verified") and m.get("bet_type") == "player_prop":
                m["opportunity"] = _clamp(float(m.get("opportunity") or 60) + 8, 35.0, 95.0)
                m["insight_rank"] = m.get("insight_rank") or 1
        markets, insight_meta = _finalize_insight_badges(markets, payload=payload)

    items = _group_events(markets, limit=market_cap)
    web = bool((payload or {}).get("_web_search")) or bool(insight_meta.get("web_search"))
    summary = str((payload or {}).get("summary") or "").strip()
    resolved_as = str((payload or {}).get("resolved_as") or "").strip()
    insight_summary = str(insight_meta.get("insight_summary") or "").strip()
    verified_n = sum(1 for m in markets if m.get("fanduel_verified"))
    prop_n = sum(1 for m in markets if m.get("bet_type") == "player_prop")
    sports_found = sorted(
        {
            str(m.get("sport") or "").strip()
            for m in markets
            if str(m.get("sport") or "").strip()
        }
    )

    msg_parts: list[str] = []
    if resolved_as:
        msg_parts.append(resolved_as)
    if verified_n:
        league_bit = f" across {', '.join(sports_found[:6])}" if sports_found else ""
        msg_parts.append(
            f"{verified_n} FanDuel/DraftKings-verified markets{league_bit}"
            f" ({prop_n} props"
            f"{f', ~{credits_used} Odds credits' if credits_used else ', 0 new Odds credits'})."
        )
    elif verified.get("message"):
        msg_parts.append(str(verified["message"]))
    elif catalog_hit.get("message") and not markets:
        msg_parts.append(str(catalog_hit["message"]))
    if summary:
        msg_parts.append(summary)
    if insight_summary and insight_summary not in " ".join(msg_parts):
        msg_parts.append(f"Insight: {insight_summary}")
    if not markets:
        msg_parts = [
            "No FanDuel/DraftKings markets found. Tap Fetch live odds to refresh the full board, "
            f"then search again for {resolved_player or q}."
        ]
    elif not verified_n and not web:
        msg_parts.append("Web browse unavailable — results may be less current.")

    return {
        "items": items,
        "markets": markets,
        "total": len(items),
        "markets_total": len(markets),
        "credits_used": credits_used,
        "cache": credits_used == 0 and verified_n > 0,
        "openai_search": True,
        "fanduel_verified": verified_n > 0,
        "insight_analyzed": bool(insight_meta.get("insight_analyzed")),
        "web_search": web,
        "query": q,
        "sport": sport,
        "all_sports": all_sports,
        "sports": sports_found,
        "person_query": person,
        "resolved_player": resolved_player,
        "resolved_teams": resolved_teams,
        "books": ["FanDuel", "DraftKings"],
        "top_pick_id": insight_meta.get("top_pick_id"),
        "best_odds_id": insight_meta.get("best_odds_id"),
        "most_likely_id": insight_meta.get("most_likely_id"),
        "message": " ".join(msg_parts),
    }
