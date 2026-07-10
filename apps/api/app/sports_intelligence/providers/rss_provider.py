"""RSS/news provider — reuses authorized sports RSS feeds."""

from __future__ import annotations

import logging
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
        items: list[RawIntelligenceItem] = []
        for row in matched:
            title = str(row.get("title") or "")
            summary = str(row.get("summary") or title)[:500]
            source_type = "injury_update" if _is_injury_headline(title, summary) else "news_article"
            items.append(
                RawIntelligenceItem(
                    external_id=str(row.get("url") or row.get("title") or ""),
                    source_type=source_type,
                    title=title,
                    summary=summary,
                    source_url=row.get("url"),
                    published_at=row.get("published_at"),
                    author_name=str(row.get("source") or "RSS"),
                    teams_mentioned=_teams_from_row(row, params),
                    injury_mentions=_injury_from_headline(title, summary) if source_type == "injury_update" else [],
                    raw_metadata={"relevance_score": row.get("relevance_score")},
                )
            )
        return items


def _is_injury_headline(title: str, summary: str) -> bool:
    hay = f"{title} {summary}".lower()
    return any(w in hay for w in ("injury", "injured", "out ", "questionable", "doubtful", "sidelined", "ruled out"))


def _injury_from_headline(title: str, summary: str) -> list[dict[str, str]]:
    return [{"note": f"{title}. {summary}"[:240]}]


def _teams_from_row(row: dict[str, Any], params: dict[str, Any]) -> list[str]:
    tokens = row.get("matched_tokens") or []
    teams = [str(params.get("home_team") or ""), str(params.get("away_team") or "")]
    return [t for t in teams if t] or [str(t) for t in tokens[:2]]
