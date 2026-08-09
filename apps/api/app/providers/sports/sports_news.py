"""Sports headlines for bet context (RSS, no API key)."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "ProjectAtlas/1.0 (sports-analysis; +https://github.com)"

SPORTS_RSS_FEEDS = [
    ("espn", "https://www.espn.com/espn/rss/news"),
    ("espn_mlb", "https://www.espn.com/espn/rss/mlb/news"),
    ("espn_nba", "https://www.espn.com/espn/rss/nba/news"),
    ("espn_nfl", "https://www.espn.com/espn/rss/nfl/news"),
    ("espn_nhl", "https://www.espn.com/espn/rss/nhl/news"),
    ("espn_soccer", "https://www.espn.com/espn/rss/soccer/news"),
    ("cbssports", "https://www.cbssports.com/rss/headlines/"),
    ("bbc_sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
]

SPORT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "NFL": ("nfl", "football", "quarterback", "touchdown", "super bowl"),
    "NBA": ("nba", "basketball", "lakers", "celtics", "playoffs"),
    "WNBA": ("wnba", "women's basketball", "aces", "liberty", "fever"),
    "MLB": ("mlb", "baseball", "pitcher", "home run", "world series", "inning"),
    "NHL": ("nhl", "hockey", "stanley cup", "goalie"),
    # Keep MLS scoped — do NOT pull EPL/UCL headlines into MLS matchups.
    "MLS": ("mls", "major league soccer", "liga mx"),
    "EPL": ("epl", "premier league", "arsenal", "liverpool", "manchester"),
    "UFC": ("ufc", "mma", "fight", "octagon"),
    "Boxing": ("boxing", "heavyweight", "title fight", "knockout"),
    "Tennis": ("tennis", "wimbledon", "us open", "atp", "wta"),
    "Golf": ("golf", "pga", "the open", "masters", "ryder cup"),
}

# Headlines with these terms are not news for the listed sport.
SPORT_CONFLICTS: dict[str, tuple[str, ...]] = {
    "MLB": (
        "soccer",
        "usmnt",
        "uswnt",
        "world cup",
        "fifa",
        "uefa",
        "premier league",
        "champions league",
        "la liga",
        "bundesliga",
        "serie a",
        "mls",
        "belgium",
        "goalkeeper",
        "striker",
        "midfielder",
        "penalty kick",
        "touchdown",
        "quarterback",
        "nba",
        "nfl",
        "nhl",
        "stanley cup",
        "ufc",
        "mma",
    ),
    "NBA": (
        "world cup",
        "touchdown",
        "quarterback",
        "home run",
        "pitcher",
        "mlb",
        "nfl",
        "stanley cup",
        "usmnt",
        "fifa",
        "nhl",
        "ufc",
        "wnba",
    ),
    "WNBA": (
        "nba",
        "nfl",
        "mlb",
        "nhl",
        "touchdown",
        "home run",
        "pitcher",
        "ufc",
        "premier league",
    ),
    "NFL": (
        "world cup",
        "home run",
        "pitcher",
        "mlb",
        "nba",
        "slam dunk",
        "usmnt",
        "fifa",
        "stanley cup",
        "nhl",
        "ufc",
    ),
    "NHL": (
        "touchdown",
        "quarterback",
        "home run",
        "mlb",
        "nba",
        "usmnt",
        "fifa",
        "premier league",
        "nfl",
        "ufc",
    ),
    "MLS": (
        "touchdown",
        "quarterback",
        "home run",
        "pitcher",
        "mlb",
        "nba",
        "nfl",
        "nhl",
        "premier league",
        "champions league",
        "la liga",
        "bundesliga",
        "serie a",
        "epl",
    ),
    "EPL": (
        "mls",
        "major league soccer",
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "touchdown",
        "home run",
        "ufc",
    ),
    "UFC": (
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "premier league",
        "touchdown",
        "home run",
        "soccer",
    ),
    "Boxing": ("ufc", "mma", "nfl", "nba", "mlb", "nhl", "soccer"),
    "Tennis": ("nfl", "nba", "mlb", "nhl", "ufc", "soccer", "touchdown"),
    "Golf": ("nfl", "nba", "mlb", "nhl", "ufc", "soccer", "touchdown"),
}

# Ambiguous shared mascots — require a multi-word / city+mascot hit.
AMBIGUOUS_MASCOTS = frozenset(
    {
        "united",
        "city",
        "rangers",
        "giants",
        "kings",
        "jets",
        "cardinals",
        "panthers",
        "wild",
        "fc",
        "athletic",
        "royale",
        "stars",
        "fire",
    }
)

# Keep short but distinctive mascots that are otherwise stripped by len>=4.
SHORT_MASCOT_ALLOW = frozenset({"sox", "avs", "avs.", "red sox", "white sox"})

MIN_NEWS_MATCH_SCORE = 6.5
MIN_PRIMARY_HITS = 1


@dataclass
class TeamMatchTokens:
    primary: tuple[str, ...]
    secondary: tuple[str, ...]
    selection_primary: tuple[str, ...] = ()
    event_sides: tuple[str, ...] = ()

    @property
    def display_names(self) -> list[str]:
        """Human labels for matched teams (mascot / full name)."""
        return [t.title() for t in self.primary if " " in t or len(t) >= 5][:4]


async def fetch_sports_news(*, limit_per_feed: int = 12) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
        for source, url in SPORTS_RSS_FEEDS:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue
                items.extend(_parse_rss(response.text, source=source, limit=limit_per_feed))
            except Exception as exc:
                logger.warning("Sports RSS %s failed: %s", source, exc)
    return _dedupe(items)


def _parse_rss(xml_text: str, *, source: str, limit: int) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    rows: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        desc = _strip_html(_text(item.find("description")))
        pub = _text(item.find("pubDate"))
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                published = None
        if not title:
            continue
        rows.append(
            {
                "source": source,
                "title": title,
                "url": link,
                "summary": desc[:500],
                "published_at": published,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = item.get("title", "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _contains_phrase(hay: str, phrase: str) -> bool:
    if not phrase:
        return False
    return bool(re.search(rf"\b{re.escape(phrase)}\b", hay, flags=re.IGNORECASE))


def _clean_team_phrase(text: str) -> str:
    cleaned = re.sub(r"[^\w\s'-]", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _clean_selection_team(selection: str) -> str:
    """Strip spread/total numbers — 'Seattle Mariners -1.5' -> 'Seattle Mariners'."""
    text = str(selection or "").strip()
    text = re.sub(r"\s*[+-]?\d+\.?\d*\s*$", "", text).strip()
    if text.lower().startswith(("over ", "under ")):
        return ""
    return _clean_team_phrase(text)


def _add_team_tokens(tokens: TeamMatchTokens, team_phrase: str) -> TeamMatchTokens:
    primary = set(tokens.primary)
    secondary = set(tokens.secondary)
    cleaned = _clean_team_phrase(team_phrase)
    if len(cleaned) < 3:
        return TeamMatchTokens(
            tuple(sorted(primary)),
            tuple(sorted(secondary)),
            tokens.selection_primary,
            tokens.event_sides,
        )

    words = [w for w in cleaned.split() if w]
    low = cleaned.lower()
    primary.add(low)

    if len(words) >= 2:
        mascot = words[-1].lower()
        # Keep short distinctive mascots (sox); skip ultra-generic 3-letter tokens.
        if len(mascot) >= 4 or mascot in SHORT_MASCOT_ALLOW:
            primary.add(mascot)
        city = " ".join(words[:-1]).lower()
        if city and city != mascot:
            secondary.add(city)
    elif len(words) == 1 and len(words[0]) >= 5:
        primary.add(words[0].lower())

    return TeamMatchTokens(
        tuple(sorted(primary)),
        tuple(sorted(secondary)),
        tokens.selection_primary,
        tokens.event_sides,
    )


def extract_event_tokens(event_name: str, selection: str) -> TeamMatchTokens:
    """
    Primary tokens = full team name or mascot (required for a match).
    Secondary = city-only phrases — never sufficient on their own.
    """
    tokens = TeamMatchTokens(primary=(), secondary=())
    sides: list[str] = []

    for part in re.split(r"\s+(?:vs\.?|v\.?|@|at)\s+", event_name, flags=re.I):
        cleaned = _clean_team_phrase(part)
        if cleaned:
            sides.append(cleaned.lower())
        tokens = _add_team_tokens(tokens, part)

    selection_team = _clean_selection_team(selection)
    selection_primary: set[str] = set()
    if selection_team:
        tokens = _add_team_tokens(tokens, selection_team)
        # Full selection phrase + its mascot count as the selected side.
        selection_primary.add(selection_team.lower())
        sel_words = selection_team.lower().split()
        if sel_words:
            mascot = sel_words[-1]
            if len(mascot) >= 4 or mascot in SHORT_MASCOT_ALLOW:
                selection_primary.add(mascot)

    # Drop very short primary tokens that cause noise — keep allowlisted short mascots.
    primary = tuple(
        t
        for t in tokens.primary
        if len(t) >= 4 or " " in t or t in SHORT_MASCOT_ALLOW
    )
    secondary = tuple(t for t in tokens.secondary if len(t) >= 4)
    sel_primary = tuple(
        t
        for t in selection_primary
        if len(t) >= 4 or " " in t or t in SHORT_MASCOT_ALLOW
    )
    return TeamMatchTokens(
        primary=primary,
        secondary=secondary,
        selection_primary=sel_primary,
        event_sides=tuple(sides),
    )


def _sport_keywords(sport: str) -> tuple[str, ...]:
    upper = sport.upper()
    for key, words in SPORT_KEYWORDS.items():
        if key in upper or upper in key:
            return words
    return (sport.lower(),)


def _sport_conflicts(sport: str) -> tuple[str, ...]:
    upper = sport.upper()
    for key, words in SPORT_CONFLICTS.items():
        if key in upper or upper in key:
            return words
    return ()


def _has_sport_conflict(sport: str, hay: str) -> bool:
    for word in _sport_conflicts(sport):
        if _contains_phrase(hay, word):
            return True
    return False


def _has_sport_signal(hay: str, sport_words: tuple[str, ...]) -> bool:
    return any(_contains_phrase(hay, word) for word in sport_words)


def _score_headline(
    hay: str,
    tokens: TeamMatchTokens,
    sport_words: tuple[str, ...],
) -> tuple[float, int, list[str], int]:
    """Return score, primary_hits, matched tokens, and distinct event-side hits."""
    score = 0.0
    primary_hits = 0
    matched: list[str] = []
    side_hits = 0

    for token in tokens.primary:
        if not _contains_phrase(hay, token):
            continue
        # Ambiguous single-token mascots alone are weak — only count with full phrase.
        if " " not in token and token in AMBIGUOUS_MASCOTS:
            # Only count if a fuller primary (city + mascot) also hit, scored later.
            continue
        weight = 6.0 if " " in token else 5.0
        if token in SHORT_MASCOT_ALLOW and " " not in token:
            weight = 5.5
        score += weight
        primary_hits += 1
        matched.append(token)

    # Count ambiguous mascot only when multi-word side phrase also matches.
    for token in tokens.primary:
        if " " in token or token not in AMBIGUOUS_MASCOTS:
            continue
        if not _contains_phrase(hay, token):
            continue
        fuller = any((" " in p and token in p and _contains_phrase(hay, p)) for p in tokens.primary)
        if fuller:
            continue  # already counted via fuller phrase
        # City+mascot not present — do not count bare "united"/"rangers".
        continue

    for token in tokens.secondary:
        if _contains_phrase(hay, token):
            score += 1.0
            matched.append(token)

    sides_matched: set[str] = set()
    ambiguous_sides: set[str] = set()
    for side in tokens.event_sides:
        if not side:
            continue
        if _contains_phrase(hay, side):
            sides_matched.add(side)
            continue
        words = side.split()
        if not words:
            continue
        mascot = words[-1]
        if not ((len(mascot) >= 4 or mascot in SHORT_MASCOT_ALLOW) and _contains_phrase(hay, mascot)):
            continue
        # Ambiguous bare mascot (rangers/united) is only a soft side hit.
        if mascot in AMBIGUOUS_MASCOTS and not _contains_phrase(hay, side):
            ambiguous_sides.add(side)
            continue
        sides_matched.add(side)
    # If one clear side hit exists, allow an ambiguous opposite mascot (e.g. Sounders + Galaxy).
    if sides_matched and ambiguous_sides:
        sides_matched.update(ambiguous_sides)
    side_hits = len(sides_matched)

    if _has_sport_signal(hay, sport_words):
        score += 1.5

    return score, primary_hits, matched, side_hits


def _passes_match_gate(
    *,
    sport: str,
    hay: str,
    tokens: TeamMatchTokens,
    sport_words: tuple[str, ...],
    score: float,
    primary_hits: int,
    side_hits: int,
    matched_tokens: list[str],
) -> bool:
    """Strict board verification — both sides or selection side + sport."""
    if primary_hits < MIN_PRIMARY_HITS or score < MIN_NEWS_MATCH_SCORE:
        return False

    sport_hit = _has_sport_signal(hay, sport_words)
    # When we know the sport vocabulary, require a sport signal OR two-team matchup hit.
    known_sport = any(k.upper() in sport.upper() for k in SPORT_KEYWORDS)
    if known_sport and not sport_hit and side_hits < 2:
        return False

    selection_hit = any(t in matched_tokens or _contains_phrase(hay, t) for t in tokens.selection_primary)
    both_sides = side_hits >= 2
    if both_sides:
        return True
    if selection_hit and (sport_hit or score >= 11.0):
        return True
    # Totals / props without a clean selection team: require both event sides.
    if not tokens.selection_primary:
        return both_sides and sport_hit
    return False


def _match_percent(score: float, primary_hits: int) -> int:
    """0–100 relevance for UI (not a statistical probability)."""
    pct = int(35 + score * 4 + primary_hits * 12)
    return max(0, min(100, pct))


def match_news_to_signal(
    signal: dict[str, Any],
    news_pool: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    event_name = str(signal.get("event_name") or "")
    selection = str(signal.get("selection") or "")
    sport = str(signal.get("sport") or "")
    tokens = extract_event_tokens(event_name, selection)
    sport_words = _sport_keywords(sport)

    if not tokens.primary:
        return []

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for item in news_pool:
        hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if _has_sport_conflict(sport, hay):
            continue

        score, primary_hits, matched_tokens, side_hits = _score_headline(hay, tokens, sport_words)
        if not _passes_match_gate(
            sport=sport,
            hay=hay,
            tokens=tokens,
            sport_words=sport_words,
            score=score,
            primary_hits=primary_hits,
            side_hits=side_hits,
            matched_tokens=matched_tokens,
        ):
            continue

        pct = _match_percent(score, primary_hits)
        scored.append(
            (
                score,
                primary_hits,
                {
                    **item,
                    "relevance_score": pct,
                    "matched_tokens": matched_tokens,
                    "context_tier": "matchup",
                    "side_hits": side_hits,
                },
            )
        )

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]


def match_news_for_insight(
    signal: dict[str, Any],
    news_pool: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Broader matching for Atlas insight — verified matchup hits first, then softer
    team/sport context for the model (not for board "verified news").
    """
    direct = match_news_to_signal(signal, news_pool, limit=limit)
    if len(direct) >= 3:
        return direct

    sport = str(signal.get("sport") or "")
    event_name = str(signal.get("event_name") or "")
    selection = str(signal.get("selection") or "")
    tokens = extract_event_tokens(event_name, selection)
    sport_words = _sport_keywords(sport)
    seen = {str(n.get("url") or n.get("title") or "") for n in direct}
    soft: list[tuple[float, dict[str, Any]]] = []

    for item in news_pool:
        key = str(item.get("url") or item.get("title") or "")
        if key in seen:
            continue
        hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if _has_sport_conflict(sport, hay):
            continue

        score, primary_hits, matched, side_hits = _score_headline(hay, tokens, sport_words)
        selection_hit = any(_contains_phrase(hay, t) for t in tokens.selection_primary)
        # Soft team context: selection side named, or both sides — never bare sport only.
        if primary_hits >= 1 and (selection_hit or side_hits >= 2):
            soft.append(
                (
                    score + 10,
                    {
                        **item,
                        "relevance_score": _match_percent(max(score, 3.0), max(primary_hits, 0)),
                        "matched_tokens": matched,
                        "context_tier": "team",
                    },
                )
            )

    soft.sort(key=lambda x: x[0], reverse=True)
    for _, item in soft:
        key = str(item.get("url") or item.get("title") or "")
        if key in seen:
            continue
        direct.append(item)
        seen.add(key)
        if len(direct) >= limit:
            break

    # Still thin — attach top sport-tagged headlines as general LLM context only.
    if len(direct) < 3 and sport_words:
        for item in news_pool:
            if len(direct) >= limit:
                break
            key = str(item.get("url") or item.get("title") or "")
            if key in seen:
                continue
            hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            if _has_sport_conflict(sport, hay):
                continue
            if any(_contains_phrase(hay, w) for w in sport_words):
                direct.append(
                    {
                        **item,
                        "relevance_score": 40,
                        "matched_tokens": [],
                        "context_tier": "sport",
                    }
                )
                seen.add(key)

    return direct[:limit]


def build_news_analysis(
    signal: dict[str, Any],
    news_items: list[dict[str, Any]],
) -> dict[str, str]:
    """Attach news only when headlines match team/mascot names — not city-only mentions."""
    base_explanation = str(signal.get("explanation") or "")
    selection = signal.get("selection") or "this side"
    event = signal.get("event_name") or "the matchup"
    edge = (signal.get("scoring_snapshot") or {}).get("edge_pct") or (
        (signal.get("line_movement") or {}).get("edge_pct")
    )

    if not news_items:
        return {
            "explanation": base_explanation,
            "bull_case": str(signal.get("bull_case") or ""),
            "bear_case": str(signal.get("bear_case") or ""),
            "analysis_summary": (
                f"No verified headlines for {event} in our feed. "
                f"This pick is driven by {edge}% edge vs the market median across books."
            ),
            "news_verified": False,
        }

    headlines = [n["title"] for n in news_items[:3]]
    headline_text = "; ".join(headlines)

    tokens = extract_event_tokens(str(event), str(selection))
    team_labels = tokens.display_names or [t.title() for t in tokens.primary[:2]]
    team_label = ", ".join(team_labels) if team_labels else "the teams in this bet"

    news_block = (
        f"Verified headlines naming {team_label}: {headline_text}. "
        f"Confirm lineups/injuries before betting — edge is still {edge}% vs median."
    )
    bull = str(signal.get("bull_case") or "")
    if headlines:
        bull = f"{bull} Related: {headlines[0]}".strip()
    bear = (
        f"{str(signal.get('bear_case') or '')} "
        f"Breaking injury or lineup news can erase this edge — re-check before lock."
    ).strip()

    return {
        "explanation": base_explanation,
        "bull_case": bull,
        "bear_case": bear,
        "analysis_summary": news_block,
        "news_verified": True,
    }
