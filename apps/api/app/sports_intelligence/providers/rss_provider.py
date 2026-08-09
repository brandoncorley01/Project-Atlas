"""RSS/news provider — reuses authorized sports RSS feeds."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.providers.sports.sports_news import (
    AMBIGUOUS_MASCOTS,
    _contains_phrase,
    fetch_sports_news,
    match_news_to_signal,
)
from app.sports_intelligence.providers.base import SportsIntelligenceProvider
from app.sports_intelligence.types import RawIntelligenceItem

logger = logging.getLogger(__name__)

_LEAN_WORDS = (
    "favor",
    "favours",
    "lean",
    "likes",
    "backing",
    "pick",
    "value",
    "covers",
    "beat",
    "edge",
    "best bet",
    "recommend",
    "projected winner",
    "our pick",
    "should cover",
    "can win",
)

_PICK_PHRASES = (
    "best bet",
    "our pick",
    "pick:",
    "leans ",
    "lean ",
    "favor ",
    "favours ",
    "take the ",
    "backing ",
    "recommend ",
)


class RssNewsIntelligenceProvider(SportsIntelligenceProvider):
    id = "rss_news"
    name = "Sports RSS Headlines"
    source_type = "news_article"
    reliability_score = 0.55

    def is_enabled(self) -> bool:
        return settings.is_intelligence_enabled()

    async def fetch_event_content(self, params: dict[str, Any]) -> list[RawIntelligenceItem]:
        signal = params.get("signal") or {}
        if not signal:
            signal = {
                "event_name": f"{params.get('away_team')} @ {params.get('home_team')}",
                "selection": params.get("selection") or params.get("home_team") or "",
                "sport": params.get("league") or "",
            }

        try:
            pool = await fetch_sports_news(limit_per_feed=12)
        except Exception as exc:
            logger.warning("RSS intelligence fetch failed: %s", exc)
            return []

        matched = match_news_to_signal(signal, pool, limit=8)
        atlas_selection = str(signal.get("selection") or params.get("selection") or "")
        home = str(params.get("home_team") or "")
        away = str(params.get("away_team") or "")
        items: list[RawIntelligenceItem] = []
        for row in matched:
            title = str(row.get("title") or "")
            summary = str(row.get("summary") or title)[:500]
            source_type = "injury_update" if _is_injury_headline(title, summary) else "news_article"
            predicted = _infer_supported_selection(title, summary, atlas_selection, home, away)
            # Only promote to analyst_pick when the headline is an explicit lean/pick.
            is_analyst = bool(predicted) and _has_explicit_pick_language(title, summary)
            items.append(
                RawIntelligenceItem(
                    external_id=str(row.get("url") or row.get("title") or ""),
                    source_type="analyst_pick" if is_analyst else source_type,
                    title=title,
                    summary=summary,
                    source_url=row.get("url"),
                    published_at=row.get("published_at"),
                    author_name=str(row.get("source") or "Sports media"),
                    predicted_selection=predicted if is_analyst else None,
                    predicted_market=str(signal.get("bet_type") or "") or None,
                    key_arguments=[summary[:180]] if is_analyst else [],
                    teams_mentioned=_teams_from_row(row, params),
                    injury_mentions=_injury_from_headline(title, summary) if source_type == "injury_update" else [],
                    raw_metadata={
                        "relevance_score": row.get("relevance_score"),
                        "supports_atlas": bool(is_analyst),
                        "source_name": str(row.get("source") or "Sports media"),
                        "context_tier": row.get("context_tier"),
                    },
                )
            )
        return items


def _has_explicit_pick_language(title: str, summary: str) -> bool:
    hay = f"{title} {summary}".lower()
    if any(p in hay for p in _PICK_PHRASES):
        return True
    return any(_contains_phrase(hay, w) for w in ("favor", "favours", "lean", "best bet", "covers"))


def _infer_supported_selection(
    title: str,
    summary: str,
    atlas_selection: str,
    home: str,
    away: str,
) -> str | None:
    """Return Atlas selection when the headline clearly backs that side — else None."""
    if not atlas_selection:
        return None
    hay = f"{title} {summary}".lower()
    sel = atlas_selection.lower().strip()
    # Totals
    if sel in {"over", "under"}:
        if not _contains_phrase(hay, sel):
            return None
        if any(w in hay for w in ("over", "under", "total", "o/u")):
            opposite = "under" if sel == "over" else "over"
            if _contains_phrase(hay, opposite) and hay.find(sel) > hay.find(opposite):
                return None
            return atlas_selection
        return None

    # Prefer full selection / full team phrases with word boundaries.
    team_phrases = [sel]
    for team in (home, away):
        t = str(team or "").strip().lower()
        if t and (t in sel or sel in t):
            team_phrases.append(t)

    named_side = False
    for phrase in team_phrases:
        if not phrase:
            continue
        if _contains_phrase(hay, phrase):
            named_side = True
            break
        words = [w for w in re.split(r"[\s/]+", phrase) if len(w) > 2]
        if not words:
            continue
        # Require city+mascot for ambiguous mascots; otherwise mascot word-boundary is OK.
        mascot = words[-1]
        if mascot in AMBIGUOUS_MASCOTS:
            if len(words) >= 2 and _contains_phrase(hay, " ".join(words)):
                named_side = True
                break
            continue
        if _contains_phrase(hay, mascot) and (
            len(words) == 1 or _contains_phrase(hay, words[0]) or _contains_phrase(hay, phrase)
        ):
            named_side = True
            break

    if not named_side:
        return None

    negative = (
        "injury",
        "injured",
        "out for",
        "ruled out",
        "doubtful",
        "suspend",
        "blowout loss",
        "eliminated",
        "benched",
    )
    if any(n in hay for n in negative) and not any(
        w in hay for w in ("despite", "returns", "cleared", "expected to play")
    ):
        return None

    # Require lean/pick language — mere name mention is news, not analyst backing.
    if not any(_contains_phrase(hay, w) if " " not in w else w in hay for w in _LEAN_WORDS):
        return None
    return atlas_selection


def _is_injury_headline(title: str, summary: str) -> bool:
    hay = f"{title} {summary}".lower()
    return any(w in hay for w in ("injury", "injured", "out ", "questionable", "doubtful", "sidelined", "ruled out"))


def _injury_from_headline(title: str, summary: str) -> list[dict[str, str]]:
    return [{"note": f"{title}. {summary}"[:240]}]


def _teams_from_row(row: dict[str, Any], params: dict[str, Any]) -> list[str]:
    tokens = row.get("matched_tokens") or []
    teams = [str(params.get("home_team") or ""), str(params.get("away_team") or "")]
    return [t for t in teams if t] or [str(t) for t in tokens[:2]]
