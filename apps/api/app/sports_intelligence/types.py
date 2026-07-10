"""Sports intelligence layer — types and data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SourceType = Literal[
    "news_article",
    "analyst_pick",
    "expert_prediction",
    "injury_update",
    "video_analysis",
    "podcast_analysis",
    "social_commentary",
    "official_team_update",
    "market_analysis",
]

Sentiment = Literal["strong_home", "lean_home", "neutral", "lean_away", "strong_away"]

ConfidenceLabel = Literal[
    "Avoid",
    "Low Confidence",
    "Lean",
    "Moderate",
    "Strong",
    "High Conviction",
]

ItemStatus = Literal["active", "superseded", "duplicate", "invalid"]

LearningMode = Literal["off", "observe", "manual_approval", "automatic"]


@dataclass
class RawIntelligenceItem:
    external_id: str | None
    source_type: SourceType
    title: str
    summary: str
    source_url: str | None = None
    published_at: str | None = None
    author_name: str | None = None
    predicted_market: str | None = None
    predicted_selection: str | None = None
    predicted_line: float | None = None
    predicted_odds: int | None = None
    confidence_text: str | None = None
    teams_mentioned: list[str] = field(default_factory=list)
    players_mentioned: list[str] = field(default_factory=list)
    key_arguments: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    injury_mentions: list[dict[str, Any]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SportsIntelligenceItem:
    id: str | None
    provider_id: str
    source_name: str
    source_url: str | None
    event_id: str | None
    signal_id: str | None
    source_type: SourceType
    title: str
    summary: str
    published_at: str | None
    ingested_at: str
    author_name: str | None = None
    predicted_side: str | None = None
    predicted_market: str | None = None
    predicted_selection: str | None = None
    predicted_line: float | None = None
    predicted_odds: int | None = None
    confidence_score: float | None = None
    teams_mentioned: list[str] = field(default_factory=list)
    players_mentioned: list[str] = field(default_factory=list)
    key_arguments: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    injury_mentions: list[dict[str, Any]] = field(default_factory=list)
    sentiment: Sentiment = "neutral"
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    source_reliability_score: float = 0.5
    duplicate_group_id: str | None = None
    content_hash: str | None = None
    status: ItemStatus = "active"


@dataclass
class ExtractedAnalystClaim:
    is_prediction: bool
    league: str
    event_match_confidence: float
    market_type: str | None = None
    selection: str | None = None
    line: float | None = None
    odds: int | None = None
    analyst_confidence: float | None = None
    supporting_reasons: list[str] = field(default_factory=list)
    opposing_reasons: list[str] = field(default_factory=list)
    injury_factors: list[str] = field(default_factory=list)
    price_sensitivity: str | None = None


@dataclass
class IntelligenceConsensus:
    signal_id: str
    event_id: str | None
    expert_count: int
    source_count: int
    home_support_pct: float | None
    away_support_pct: float | None
    top_consensus_pick: str | None
    weighted_consensus_score: float
    contrarian_summary: str | None
    majority_reasoning: list[str]
    minority_reasoning: list[str]
    key_news_summary: str | None
    injury_impact_summary: str | None
    model_agreement_status: str
    confidence_adjustment: float
    confidence_label: str
    verdict: str
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class IntelligenceAdjustment:
    signal_id: str
    original_model_confidence: float
    expert_consensus_adjustment: float
    news_adjustment: float
    injury_adjustment: float
    disagreement_penalty: float
    final_suggested_adjustment: float
    adjusted_confidence: float
    explanation: list[str]
