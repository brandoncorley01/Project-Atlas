"""End-to-end style flow for sports intelligence (in-memory)."""

from __future__ import annotations

from app.sports_intelligence.adjustment import compute_adjustment
from app.sports_intelligence.consensus import build_consensus
from app.sports_intelligence.dedup import deduplicate_items, mark_syndicate_duplicates
from app.sports_intelligence.normalization import normalize_item
from app.sports_intelligence.types import RawIntelligenceItem


def test_ingest_consensus_adjustment_flow():
    signal = {
        "id": "signal-uuid",
        "selection": "Chiefs -3",
        "confidence_score": 68,
        "sport": "NFL",
        "event_name": "Bills @ Chiefs",
        "scoring_snapshot": {"home_team": "Chiefs", "away_team": "Bills", "event_id": "evt-1"},
    }
    home, away = "Chiefs", "Bills"
    raws = [
        RawIntelligenceItem(
            external_id="e1",
            source_type="expert_prediction",
            title="Expert likes Chiefs",
            summary="Chiefs at home with edge.",
            predicted_selection="Chiefs",
            author_name="Expert 1",
            key_arguments=["Home field"],
        ),
        RawIntelligenceItem(
            external_id="e2",
            source_type="expert_prediction",
            title="Contrarian Bills",
            summary="Bills defense travels.",
            predicted_selection="Bills",
            author_name="Expert 2",
            key_arguments=["Defense"],
        ),
        RawIntelligenceItem(
            external_id="n1",
            source_type="news_article",
            title="Chiefs injury watch",
            summary="Starter questionable.",
            teams_mentioned=["Chiefs"],
        ),
        RawIntelligenceItem(
            external_id="dup",
            source_type="news_article",
            title="Chiefs injury watch",
            summary="Starter questionable.",
            teams_mentioned=["Chiefs"],
        ),
    ]

    normalized = [
        normalize_item(
            r,
            provider_id="mock",
            source_name="Mock",
            signal_id=signal["id"],
            event_id="evt-1",
            reliability=0.6,
            home_team=home,
            away_team=away,
        )
        for r in raws
    ]
    unique = deduplicate_items(normalized, set())
    unique = mark_syndicate_duplicates(unique)
    active = [
        {
            "status": i.status,
            "source_type": i.source_type,
            "predicted_selection": i.predicted_selection,
            "predicted_side": i.predicted_side,
            "author_name": i.author_name,
            "source_name": i.source_name,
            "relevance_score": i.relevance_score,
            "freshness_score": i.freshness_score,
            "source_reliability_score": i.source_reliability_score,
            "confidence_score": i.confidence_score,
            "key_arguments": i.key_arguments,
            "risk_factors": i.risk_factors,
            "title": i.title,
            "summary": i.summary,
        }
        for i in unique
        if i.status == "active"
    ]

    assert len(active) < len(raws)

    consensus = build_consensus(
        signal["id"],
        "evt-1",
        active,
        model_selection=signal["selection"],
        home_team=home,
        away_team=away,
    )
    assert consensus.expert_count >= 1
    adjustment = compute_adjustment(signal, consensus, active_items=active)
    assert adjustment.original_model_confidence == 68
    assert consensus.model_agreement_status in ("agrees", "lean_agrees", "disagrees", "mixed", "no_expert_data")
