"""Options activity provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.market_intelligence.types import DataStatus, NormalizedOptionsActivity


class OptionsFlowProvider(ABC):
    id: str
    name: str
    default_status: DataStatus

    @abstractmethod
    def is_enabled(self) -> bool:
        ...

    @abstractmethod
    async def fetch_activity(self, params: dict[str, Any] | None = None) -> list[NormalizedOptionsActivity]:
        """Return normalized activity. Must never fabricate dark-pool or institutional IDs."""

    def status_payload(self) -> dict[str, Any]:
        return {
            "provider_id": self.id,
            "provider_name": self.name,
            "enabled": self.is_enabled(),
            "default_data_status": self.default_status.value,
        }
