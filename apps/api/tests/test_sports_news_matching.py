"""Strict sports news matching — avoid wrong-event headlines and catch real matchups."""

from __future__ import annotations

from app.providers.sports.sports_news import (
    extract_event_tokens,
    match_news_for_insight,
    match_news_to_signal,
)
from app.sports_intelligence.providers.rss_provider import _infer_supported_selection


def _pool(*titles: str) -> list[dict]:
    return [{"title": t, "summary": "", "url": f"https://example.com/{i}", "source": "test"} for i, t in enumerate(titles)]


def test_yankees_red_sox_matchup_headline_attaches():
    signal = {
        "event_name": "New York Yankees vs Boston Red Sox",
        "selection": "New York Yankees",
        "sport": "MLB",
    }
    matched = match_news_to_signal(
        signal,
        _pool("Yankees blank Red Sox in Bronx opener", "Premier League title race heats up"),
    )
    assert len(matched) == 1
    assert "Yankees" in matched[0]["title"]


def test_mls_sounders_rejects_manchester_united_and_epl():
    signal = {
        "event_name": "Seattle Sounders vs LA Galaxy",
        "selection": "Seattle Sounders",
        "sport": "MLS",
    }
    matched = match_news_to_signal(
        signal,
        _pool(
            "Manchester United win again in Premier League",
            "Champions League draw announced",
            "Sounders and Galaxy set for Cascadia clash in MLS",
        ),
    )
    titles = " ".join(m["title"] for m in matched)
    assert "Manchester" not in titles
    assert "Champions League" not in titles
    assert "Sounders" in titles


def test_texas_rangers_does_not_take_ny_rangers_hockey():
    signal = {
        "event_name": "Texas Rangers vs Houston Astros",
        "selection": "Texas Rangers",
        "sport": "MLB",
    }
    matched = match_news_to_signal(
        signal,
        _pool(
            "New York Rangers win in overtime thriller",
            "Texas Rangers edge Astros in AL West showdown",
        ),
    )
    assert len(matched) == 1
    assert "Texas Rangers" in matched[0]["title"]


def test_opponent_only_headline_not_enough():
    signal = {
        "event_name": "Dallas Cowboys vs Philadelphia Eagles",
        "selection": "Dallas Cowboys",
        "sport": "NFL",
    }
    matched = match_news_to_signal(
        signal,
        _pool("Eagles injury report: starter questionable for Sunday"),
    )
    assert matched == []


def test_insight_soft_sport_tier_not_used_as_verified_path():
    signal = {
        "event_name": "Seattle Sounders vs LA Galaxy",
        "selection": "Seattle Sounders",
        "sport": "MLS",
    }
    # Insight may keep sport context for the model, but strict matcher must stay empty here.
    soft = match_news_for_insight(
        signal,
        _pool("MLS weekend preview: what to watch across the league"),
        limit=4,
    )
    strict = match_news_to_signal(signal, soft)
    assert strict == []
    assert all(n.get("context_tier") == "sport" for n in soft)


def test_short_mascot_sox_still_tokens():
    tokens = extract_event_tokens("Boston Red Sox vs New York Yankees", "Boston Red Sox")
    assert any("sox" in t for t in tokens.primary)


def test_analyst_inference_requires_lean_language():
    # Mere name mention is not analyst backing.
    assert (
        _infer_supported_selection(
            "Texas Rangers take batting practice",
            "",
            "Texas Rangers",
            "Texas Rangers",
            "Houston Astros",
        )
        is None
    )
    assert (
        _infer_supported_selection(
            "Best bet: Texas Rangers to cover against Astros",
            "We lean Texas Rangers tonight",
            "Texas Rangers",
            "Texas Rangers",
            "Houston Astros",
        )
        == "Texas Rangers"
    )


def test_analyst_inference_rejects_ambiguous_united():
    assert (
        _infer_supported_selection(
            "Manchester United favored to win again",
            "Pick: United",
            "Atlanta United",
            "Atlanta United",
            "Inter Miami",
        )
        is None
    )
