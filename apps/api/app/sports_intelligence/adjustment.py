"""Bounded intelligence confidence adjustments."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.sports_intelligence.types import ConfidenceLabel, IntelligenceAdjustment, IntelligenceConsensus


def confidence_label(score: float) -> ConfidenceLabel:
    if score < 40:
        return "Avoid"
    if score < 50:
        return "Low Confidence"
    if score < 60:
        return "Lean"
    if score < 70:
        return "Moderate"
    if score < 80:
        return "Strong"
    return "High Conviction"


def compute_adjustment(
    signal: dict[str, Any],
    consensus: IntelligenceConsensus,
    *,
    active_items: list[dict[str, Any]],
) -> IntelligenceAdjustment:
    original = float(signal.get("confidence_score") or 50.0)
    model_selection = str(signal.get("selection") or "")

    expert_adj = _expert_adjustment(consensus, model_selection)
    news_adj = _news_adjustment(active_items)
    injury_adj = _injury_adjustment(active_items)
    disagreement = _disagreement_penalty(consensus, model_selection)

    raw_total = expert_adj + news_adj + injury_adj - disagreement
    max_total = settings.atlas_max_total_intelligence_adjustment
    capped = max(-max_total, min(max_total, raw_total))

    adjusted = max(0.0, min(100.0, original + capped))
    explanation: list[str] = []
    if expert_adj:
        explanation.append(f"Expert consensus: {expert_adj:+.1f} pp")
    if news_adj:
        explanation.append(f"News context: {news_adj:+.1f} pp")
    if injury_adj:
        explanation.append(f"Injury signals: {injury_adj:+.1f} pp")
    if disagreement:
        explanation.append(f"Source disagreement penalty: -{disagreement:.1f} pp")
    if not explanation:
        explanation.append("No material intelligence adjustment applied")

    return IntelligenceAdjustment(
        signal_id=str(signal.get("id") or consensus.signal_id),
        original_model_confidence=original,
        expert_consensus_adjustment=expert_adj,
        news_adjustment=news_adj,
        injury_adjustment=injury_adj,
        disagreement_penalty=disagreement,
        final_suggested_adjustment=capped,
        adjusted_confidence=adjusted,
        explanation=explanation,
    )


def _expert_adjustment(consensus: IntelligenceConsensus, model_selection: str) -> float:
    cap = settings.atlas_max_expert_confidence_adjustment
    if consensus.expert_count < 1:
        return 0.0
    score = consensus.weighted_consensus_score
    pick = (consensus.top_consensus_pick or "").lower()
    model = model_selection.lower()
    agrees = pick and (pick in model or model in pick)
    direction = 1.0 if agrees else -0.6
    magnitude = min(cap, abs(score) * cap / 100.0)
    return round(direction * magnitude, 2)


def _news_adjustment(items: list[dict[str, Any]]) -> float:
    cap = settings.atlas_max_news_confidence_adjustment
    news = [i for i in items if i.get("source_type") == "news_article" and i.get("status") == "active"]
    if not news:
        return 0.0
    avg_rel = sum(float(i.get("relevance_score") or 0) for i in news) / len(news)
    return round(min(cap, avg_rel * cap * 0.5), 2)


def _injury_adjustment(items: list[dict[str, Any]]) -> float:
    injuries = [
        i
        for i in items
        if i.get("source_type") == "injury_update" and i.get("status") == "active"
    ]
    if not injuries:
        return 0.0
    return round(min(4.0, len(injuries) * 1.5), 2)


def _disagreement_penalty(consensus: IntelligenceConsensus, model_selection: str) -> float:
    if consensus.expert_count < 2:
        return 0.0
    home = consensus.home_support_pct
    away = consensus.away_support_pct
    if home is None or away is None:
        return 0.0
    spread = abs(home - away)
    if spread < 25:
        return 2.5
    pick = (consensus.top_consensus_pick or "").lower()
    model = model_selection.lower()
    if pick and pick not in model and model not in pick and spread >= 40:
        return 4.0
    return 0.0
