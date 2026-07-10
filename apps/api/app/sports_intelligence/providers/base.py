"""Provider interface for sports intelligence sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.sports_intelligence.types import RawIntelligenceItem, SourceType


class SportsIntelligenceProvider(ABC):
    id: str
    name: str
    source_type: SourceType
    reliability_score: float = 0.5

    @abstractmethod
    def is_enabled(self) -> bool:
        ...

    @abstractmethod
    async def fetch_event_content(
        self,
        params: dict[str, Any],
    ) -> list[RawIntelligenceItem]:
        """
        params: event_id, league, home_team, away_team, event_start_time, signal
        """
