"""Provider registry."""

from __future__ import annotations

from app.sports_intelligence.providers.base import SportsIntelligenceProvider
from app.sports_intelligence.providers.manual_provider import ManualExpertIntelligenceProvider
from app.sports_intelligence.providers.mock_provider import MockIntelligenceProvider
from app.sports_intelligence.providers.rss_provider import RssNewsIntelligenceProvider

_manual_provider = ManualExpertIntelligenceProvider()


def get_providers() -> list[SportsIntelligenceProvider]:
    return [
        RssNewsIntelligenceProvider(),
        _manual_provider,
        MockIntelligenceProvider(),
    ]


def get_manual_provider() -> ManualExpertIntelligenceProvider:
    return _manual_provider
