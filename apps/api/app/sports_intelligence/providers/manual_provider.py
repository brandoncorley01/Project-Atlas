"""Manual expert-pick provider — reads DB entries configured by admins."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.sports_intelligence.providers.base import SportsIntelligenceProvider
from app.sports_intelligence.types import RawIntelligenceItem


class ManualExpertIntelligenceProvider(SportsIntelligenceProvider):
    id = "manual_expert"
    name = "Manual Expert Entries"
    source_type = "expert_prediction"
    reliability_score = 0.7

    def __init__(self, manual_rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = manual_rows or []

    def is_enabled(self) -> bool:
        return settings.is_intelligence_enabled()

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def fetch_event_content(self, params: dict[str, Any]) -> list[RawIntelligenceItem]:
        event_id = str(params.get("event_id") or "")
        signal_id = str(params.get("signal_id") or "")
        items: list[RawIntelligenceItem] = []
        for row in self._rows:
            if signal_id and str(row.get("signal_id") or "") == signal_id:
                pass
            elif event_id and str(row.get("event_id") or "") == event_id:
                pass
            else:
                continue
            items.append(
                RawIntelligenceItem(
                    external_id=str(row.get("id") or ""),
                    source_type="expert_prediction",
                    title=str(row.get("title") or row.get("selection") or "Expert pick"),
                    summary=str(row.get("summary") or ""),
                    source_url=row.get("source_url"),
                    published_at=row.get("published_at"),
                    author_name=row.get("author_name") or row.get("analyst_name"),
                    predicted_market=row.get("market_type") or row.get("predicted_market"),
                    predicted_selection=row.get("selection") or row.get("predicted_selection"),
                    predicted_line=_float_or_none(row.get("line") or row.get("predicted_line")),
                    predicted_odds=_int_or_none(row.get("odds") or row.get("predicted_odds")),
                    confidence_text=str(row.get("confidence_score") or ""),
                    key_arguments=list(row.get("supporting_reasons") or row.get("key_arguments") or []),
                    risk_factors=list(row.get("opposing_reasons") or row.get("risk_factors") or []),
                    raw_metadata={"manual": True, "item_id": row.get("id")},
                )
            )
        return items


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
