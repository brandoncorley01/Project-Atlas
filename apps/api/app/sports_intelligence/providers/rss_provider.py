"""RSS/news provider — reuses authorized sports RSS feeds."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.providers.sports.sports_news import fetch_sports_news, match_news_to_signal
from app.sports_intelligence.providers.base import SportsIntelligenceProvider
from app.sports_intelligence.types import RawIntelligenceItem

logger = logging.getLogger(__name__)


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
            items.append(
                RawIntelligenceItem(
                    external_id=str(row.get("url") or row.get("title") or ""),
                    source_type="analyst_pick" if predicted else source_type,
                    title=title,
                    summary=summary,
                    source_url=row.get("url"),
                    published_at=row.get("published_at"),
                    author_name=str(row.get("source") or "Sports media"),
                    predicted_selection=predicted,
                    predicted_market=str(signal.get("bet_type") or "") or None,
                    key_arguments=[summary[:180]] if predicted else [],
                    teams_mentioned=_teams_from_row(row, params),
                    injury_mentions=_injury_from_headline(title, summary) if source_type == "injury_update" else [],
                    raw_metadata={
                        "relevance_score": row.get("relevance_score"),
                        "supports_atlas": bool(predicted),
                        "source_name": str(row.get("source") or "Sports media"),
                    },
                )
            )
        return items


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
        if sel in hay and any(w in hay for w in ("over", "under", "total", "o/u")):
            # Avoid counting the opposite total word as support
            opposite = "under" if sel == "over" else "over"
            if opposite in hay and hay.find(sel) > hay.find(opposite):
                return None
            return atlas_selection
        return None

    # Team / side — require selection (or core team token) in headline with lean language
    tokens = [t for t in re.split(r"[\s/]+", sel) if len(t) > 2]
    if not any(t in hay for t in tokens):
        # Try home/away if selection is a formatted spread label
        for team in (home, away):
            if team and team.lower() in sel and team.lower() in hay:
                tokens = [team.lower()]
                break
        else:
            return None

    negative = (
        "injury", "injured", "out for", "ruled out", "doubtful", "suspend",
        "blowout loss", "eliminated", "benched",
    )
    if any(n in hay for n in negative) and not any(
        w in hay for w in ("despite", "returns", "cleared", "expected to play")
    ):
        return None

    lean = (
        "favor", "favours", "lean", "like", "back", "pick", "play", "value",
        "covers", "wins", "beat", "edge", "best bet", "take", "recommend",
        "unlock", "preview", "keys to", "can win", "should",
    )
    if any(w in hay for w in lean) or any(t in hay for t in tokens[:2]):
        # Headline names Atlas's side — treat as supporting context from that outlet
        return atlas_selection
    return None


def _is_injury_headline(title: str, summary: str) -> bool:
    hay = f"{title} {summary}".lower()
    return any(w in hay for w in ("injury", "injured", "out ", "questionable", "doubtful", "sidelined", "ruled out"))


def _injury_from_headline(title: str, summary: str) -> list[dict[str, str]]:
    return [{"note": f"{title}. {summary}"[:240]}]


def _teams_from_row(row: dict[str, Any], params: dict[str, Any]) -> list[str]:
    tokens = row.get("matched_tokens") or []
    teams = [str(params.get("home_team") or ""), str(params.get("away_team") or "")]
    return [t for t in teams if t] or [str(t) for t in tokens[:2]]
