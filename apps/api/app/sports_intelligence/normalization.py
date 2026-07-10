"""Normalize raw intelligence items into canonical form."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from app.sports_intelligence.types import RawIntelligenceItem, Sentiment, SportsIntelligenceItem


def content_hash(title: str, summary: str, source_url: str | None) -> str:
    base = f"{title.strip().lower()}|{summary.strip().lower()[:200]}|{source_url or ''}"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def normalize_item(
    raw: RawIntelligenceItem,
    *,
    provider_id: str,
    source_name: str,
    signal_id: str | None,
    event_id: str | None,
    reliability: float,
    home_team: str,
    away_team: str,
) -> SportsIntelligenceItem:
    now = datetime.now(UTC).isoformat()
    title = _clean_text(raw.title)
    summary = _clean_text(raw.summary)[:600]
    sentiment = infer_sentiment(raw, home_team, away_team)
    relevance = _relevance_score(raw, home_team, away_team)
    freshness = _freshness_score(raw.published_at)

    return SportsIntelligenceItem(
        id=None,
        provider_id=provider_id,
        source_name=source_name,
        source_url=raw.source_url,
        event_id=event_id,
        signal_id=signal_id,
        source_type=raw.source_type,
        title=title,
        summary=summary,
        published_at=raw.published_at,
        ingested_at=now,
        author_name=raw.author_name,
        predicted_side=_predicted_side(raw, home_team, away_team),
        predicted_market=raw.predicted_market,
        predicted_selection=raw.predicted_selection,
        predicted_line=raw.predicted_line,
        predicted_odds=raw.predicted_odds,
        confidence_score=_confidence_from_text(raw.confidence_text),
        teams_mentioned=raw.teams_mentioned or [t for t in (home_team, away_team) if t],
        players_mentioned=raw.players_mentioned,
        key_arguments=raw.key_arguments[:6],
        risk_factors=raw.risk_factors[:6],
        injury_mentions=raw.injury_mentions,
        sentiment=sentiment,
        relevance_score=relevance,
        freshness_score=freshness,
        source_reliability_score=reliability,
        content_hash=content_hash(title, summary, raw.source_url),
        status="active",
    )


def infer_sentiment(raw: RawIntelligenceItem, home_team: str, away_team: str) -> Sentiment:
    hay = f"{raw.title} {raw.summary} {raw.predicted_selection or ''}".lower()
    home_hits = _team_hits(hay, home_team)
    away_hits = _team_hits(hay, away_team)
    lean_words = ("favor", "lean", "like", "back", "pick", "play", "value")
    has_lean = any(w in hay for w in lean_words)

    if raw.source_type in ("analyst_pick", "expert_prediction") and raw.predicted_selection:
        sel = raw.predicted_selection.lower()
        if _team_hits(sel, home_team) >= 1:
            return "strong_home" if has_lean else "lean_home"
        if _team_hits(sel, away_team) >= 1:
            return "strong_away" if has_lean else "lean_away"

    if home_hits > away_hits + 1:
        return "lean_home"
    if away_hits > home_hits + 1:
        return "lean_away"
    return "neutral"


def _team_hits(hay: str, team: str) -> int:
    if not team:
        return 0
    tokens = [t for t in re.split(r"\W+", team.lower()) if len(t) > 2]
    return sum(1 for t in tokens if t in hay)


def _relevance_score(raw: RawIntelligenceItem, home_team: str, away_team: str) -> float:
    base = float(raw.raw_metadata.get("relevance_score") or 50) / 100.0
    if raw.source_type in ("analyst_pick", "expert_prediction"):
        base = max(base, 0.65)
    hay = f"{raw.title} {raw.summary}".lower()
    if _team_hits(hay, home_team) or _team_hits(hay, away_team):
        base = min(1.0, base + 0.15)
    return round(min(1.0, max(0.0, base)), 2)


def _freshness_score(published_at: str | None) -> float:
    if not published_at:
        return 0.4
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        hours = (datetime.now(UTC) - dt).total_seconds() / 3600
        if hours <= 6:
            return 1.0
        if hours <= 24:
            return 0.85
        if hours <= 72:
            return 0.6
        return 0.35
    except (TypeError, ValueError):
        return 0.4


def _confidence_from_text(text: str | None) -> float | None:
    if not text:
        return None
    hay = text.lower()
    if "high" in hay or "strong" in hay:
        return 75.0
    if "moderate" in hay or "medium" in hay:
        return 60.0
    if "lean" in hay or "low" in hay:
        return 45.0
    try:
        val = float(text)
        return max(0.0, min(100.0, val))
    except (TypeError, ValueError):
        return 55.0


def _predicted_side(raw: RawIntelligenceItem, home_team: str, away_team: str) -> str | None:
    sel = raw.predicted_selection or ""
    if _team_hits(sel.lower(), home_team):
        return "home"
    if _team_hits(sel.lower(), away_team):
        return "away"
    return None


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())
