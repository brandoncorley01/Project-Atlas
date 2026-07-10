"""Mock provider for local testing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.sports_intelligence.providers.base import SportsIntelligenceProvider
from app.sports_intelligence.types import RawIntelligenceItem


class MockIntelligenceProvider(SportsIntelligenceProvider):
    id = "mock"
    name = "Atlas Mock Intelligence"
    source_type = "analyst_pick"
    reliability_score = 0.4

    def is_enabled(self) -> bool:
        return settings.is_intelligence_enabled() and settings.environment == "development"

    async def fetch_event_content(self, params: dict[str, Any]) -> list[RawIntelligenceItem]:
        home = str(params.get("home_team") or "Home")
        away = str(params.get("away_team") or "Away")
        league = str(params.get("league") or "Sports")
        now = datetime.now(UTC).isoformat()
        return [
            RawIntelligenceItem(
                external_id=f"mock-{params.get('event_id')}-1",
                source_type="analyst_pick",
                title=f"Mock analyst leans {home} in {away} @ {home}",
                summary=(
                    f"Development mock pick for {league}: {home} has situational edges "
                    f"in recent form. Treat as test data only."
                ),
                source_url=None,
                published_at=now,
                author_name="Mock Analyst",
                predicted_market="spread",
                predicted_selection=home,
                confidence_text="moderate",
                teams_mentioned=[home, away],
                key_arguments=[f"{home} trending well at home", "Market may be slow to adjust"],
                risk_factors=["Small sample size in mock data"],
            ),
            RawIntelligenceItem(
                external_id=f"mock-{params.get('event_id')}-2",
                source_type="injury_update",
                title=f"Injury watch: {away} lineup note (mock)",
                summary=f"Mock injury headline for {away}. Verify with official sources before betting.",
                published_at=now,
                teams_mentioned=[away],
                injury_mentions=[{"player": "Starter", "status": "questionable", "team": away}],
            ),
        ]
