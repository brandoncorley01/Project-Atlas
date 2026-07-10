"""Sports intelligence unit tests."""

from __future__ import annotations

from app.sports_intelligence.adjustment import compute_adjustment, confidence_label
from app.sports_intelligence.consensus import build_consensus
from app.sports_intelligence.dedup import deduplicate_items, mark_syndicate_duplicates
from app.sports_intelligence.normalization import content_hash, normalize_item
from app.sports_intelligence.types import IntelligenceConsensus, RawIntelligenceItem, SportsIntelligenceItem


def test_content_hash_stable():
    h1 = content_hash("Title", "Summary", "https://example.com")
    h2 = content_hash("Title", "Summary", "https://example.com")
    assert h1 == h2
    assert h1 != content_hash("Other", "Summary", "https://example.com")


def test_normalize_item_sets_scores():
    raw = RawIntelligenceItem(
        external_id="1",
        source_type="analyst_pick",
        title="Lakers lean home",
        summary="Lakers have form edge at home.",
        predicted_selection="Lakers",
        confidence_text="strong",
    )
    item = normalize_item(
        raw,
        provider_id="test",
        source_name="Test",
        signal_id="sig-1",
        event_id="evt-1",
        reliability=0.6,
        home_team="Lakers",
        away_team="Celtics",
    )
    assert item.relevance_score > 0
    assert item.sentiment in ("lean_home", "strong_home")
    assert item.content_hash


def test_deduplicate_items():
    a = SportsIntelligenceItem(
        id=None,
        provider_id="p",
        source_name="S",
        source_url=None,
        event_id="e",
        signal_id="s",
        source_type="news_article",
        title="Same",
        summary="Story",
        published_at=None,
        ingested_at="now",
        content_hash="abc",
    )
    b = SportsIntelligenceItem(
        id=None,
        provider_id="p",
        source_name="S",
        source_url=None,
        event_id="e",
        signal_id="s",
        source_type="news_article",
        title="Same copy",
        summary="Story",
        published_at=None,
        ingested_at="now",
        content_hash="abc",
    )
    unique = deduplicate_items([a, b], set())
    assert len(unique) == 1
    assert b.status == "duplicate"


def test_mark_syndicate_duplicates():
    items = [
        SportsIntelligenceItem(
            id=None,
            provider_id="p1",
            source_name="A",
            source_url="u1",
            event_id="e",
            signal_id="s",
            source_type="news_article",
            title="Breaking: Team X injury update",
            summary="x",
            published_at=None,
            ingested_at="now",
            content_hash="h1",
        ),
        SportsIntelligenceItem(
            id=None,
            provider_id="p2",
            source_name="B",
            source_url="u2",
            event_id="e",
            signal_id="s",
            source_type="news_article",
            title="Breaking: Team X injury update",
            summary="x",
            published_at=None,
            ingested_at="now",
            content_hash="h2",
        ),
    ]
    mark_syndicate_duplicates(items)
    assert items[1].status == "duplicate"


def test_build_consensus_weighting():
    items = [
        {
            "status": "active",
            "source_type": "expert_prediction",
            "predicted_selection": "Lakers",
            "predicted_side": "home",
            "author_name": "Analyst A",
            "source_name": "Source 1",
            "relevance_score": 0.9,
            "freshness_score": 0.9,
            "source_reliability_score": 0.8,
            "confidence_score": 70,
            "key_arguments": ["Home court"],
            "risk_factors": ["Rest"],
        },
        {
            "status": "active",
            "source_type": "expert_prediction",
            "predicted_selection": "Celtics",
            "predicted_side": "away",
            "author_name": "Analyst B",
            "source_name": "Source 2",
            "relevance_score": 0.7,
            "freshness_score": 0.8,
            "source_reliability_score": 0.7,
            "confidence_score": 60,
            "key_arguments": ["Defense"],
            "risk_factors": ["Travel"],
        },
    ]
    consensus = build_consensus(
        "sig-1",
        "evt-1",
        items,
        model_selection="Lakers -3.5",
        home_team="Lakers",
        away_team="Celtics",
    )
    assert consensus.expert_count == 2
    assert consensus.source_count == 2
    assert consensus.top_consensus_pick in ("Lakers", "Celtics")


def test_confidence_caps():
    signal = {"id": "s1", "confidence_score": 72, "selection": "Lakers -3.5"}
    consensus = IntelligenceConsensus(
        signal_id="s1",
        event_id="e1",
        expert_count=3,
        source_count=3,
        home_support_pct=80,
        away_support_pct=20,
        top_consensus_pick="Lakers -3.5",
        weighted_consensus_score=75,
        contrarian_summary=None,
        majority_reasoning=["Form"],
        minority_reasoning=[],
        key_news_summary="News",
        injury_impact_summary=None,
        model_agreement_status="agrees",
        confidence_adjustment=0,
        confidence_label="Moderate",
        verdict="Test",
    )
    items = [
        {
            "status": "active",
            "source_type": "news_article",
            "relevance_score": 0.9,
        }
    ]
    adj = compute_adjustment(signal, consensus, active_items=items)
    assert adj.adjusted_confidence <= 100
    assert adj.final_suggested_adjustment <= 12


def test_confidence_labels():
    assert confidence_label(35) == "Avoid"
    assert confidence_label(55) == "Lean"
    assert confidence_label(85) == "High Conviction"


def test_feature_flag_defaults_off():
    from app.config import Settings

    s = Settings(atlas_expert_intelligence_enabled=False)
    assert s.is_intelligence_enabled() is False
