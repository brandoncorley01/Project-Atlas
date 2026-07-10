"""Database access for sports intelligence tables."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.sports_intelligence.types import SportsIntelligenceItem

logger = logging.getLogger(__name__)


class SportsIntelligenceDb:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def list_items_for_signal(self, signal_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "sports_intelligence_items",
            filters={
                "user_id": f"eq.{self.user_id}",
                "signal_id": f"eq.{signal_id}",
                "status": "eq.active",
            },
            order="ingested_at.desc",
            limit=50,
        )

    async def existing_hashes(self, signal_id: str) -> set[str]:
        rows = await self.db.select(
            "sports_intelligence_items",
            select="content_hash",
            filters={
                "user_id": f"eq.{self.user_id}",
                "signal_id": f"eq.{signal_id}",
            },
            limit=200,
        )
        return {str(r.get("content_hash") or "") for r in rows if r.get("content_hash")}

    async def insert_items(self, items: list[SportsIntelligenceItem]) -> list[dict[str, Any]]:
        if not items:
            return []
        rows = [_item_to_row(self.user_id, item) for item in items]
        try:
            return await self.db.insert("sports_intelligence_items", rows)
        except Exception as exc:
            logger.warning("Insert intelligence items failed: %s", exc)
            return []

    async def get_consensus(self, signal_id: str) -> dict[str, Any] | None:
        rows = await self.db.select(
            "event_intelligence_consensus",
            filters={
                "user_id": f"eq.{self.user_id}",
                "signal_id": f"eq.{signal_id}",
            },
            limit=1,
        )
        return rows[0] if rows else None

    async def upsert_consensus(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        signal_id = payload.get("signal_id")
        if not signal_id:
            return None
        existing = await self.get_consensus(str(signal_id))
        row = {**payload, "user_id": self.user_id, "updated_at": datetime.now(UTC).isoformat()}
        try:
            if existing:
                await self.db.update(
                    "event_intelligence_consensus",
                    {"id": f"eq.{existing['id']}", "user_id": f"eq.{self.user_id}"},
                    row,
                )
                return {**existing, **row}
            inserted = await self.db.insert("event_intelligence_consensus", [row])
            return inserted[0] if inserted else row
        except Exception as exc:
            logger.warning("Upsert consensus failed: %s", exc)
            return None

    async def list_manual_items(self, signal_id: str | None = None) -> list[dict[str, Any]]:
        filters: dict[str, str] = {"user_id": f"eq.{self.user_id}"}
        if signal_id:
            filters["signal_id"] = f"eq.{signal_id}"
        rows = await self.db.select(
            "sports_intelligence_items",
            filters=filters,
            order="created_at.desc",
            limit=100,
        )
        return [r for r in rows if (r.get("raw_metadata") or {}).get("manual")]

    async def insert_manual_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        row = {
            "user_id": self.user_id,
            "signal_id": entry.get("signal_id"),
            "event_id": entry.get("event_id"),
            "source_type": "expert_prediction",
            "title": entry.get("title") or entry.get("selection") or "Manual expert pick",
            "summary": entry.get("summary") or "",
            "source_url": entry.get("source_url"),
            "author_name": entry.get("analyst") or entry.get("author_name"),
            "published_at": entry.get("published_at") or datetime.now(UTC).isoformat(),
            "predicted_market": entry.get("market_type"),
            "predicted_selection": entry.get("selection"),
            "predicted_line": entry.get("line"),
            "predicted_odds": entry.get("odds"),
            "confidence_score": entry.get("confidence"),
            "key_arguments": entry.get("supporting_reasons") or [],
            "risk_factors": entry.get("risks") or [],
            "relevance_score": 0.85,
            "freshness_score": 1.0,
            "status": "active",
            "raw_metadata": {"manual": True, "source": entry.get("source")},
        }
        h = entry.get("content_hash")
        if h:
            row["content_hash"] = h
        inserted = await self.db.insert("sports_intelligence_items", [row])
        return inserted[0] if inserted else None

    async def delete_manual_entry(self, item_id: str) -> bool:
        try:
            await self.db.delete(
                "sports_intelligence_items",
                {"id": f"eq.{item_id}", "user_id": f"eq.{self.user_id}"},
            )
            return True
        except Exception as exc:
            logger.warning("Delete manual entry failed: %s", exc)
            return False

    async def provider_diagnostics(self) -> dict[str, Any]:
        today = datetime.now(UTC).date().isoformat()
        items = await self.db.select(
            "sports_intelligence_items",
            filters={"user_id": f"eq.{self.user_id}"},
            order="ingested_at.desc",
            limit=500,
        )
        ingested_today = sum(1 for i in items if str(i.get("ingested_at") or "").startswith(today))
        rejected = sum(1 for i in items if i.get("status") in ("duplicate", "invalid"))
        return {
            "items_ingested_today": ingested_today,
            "items_rejected_today": rejected,
            "total_items": len(items),
            "last_ingested_at": items[0].get("ingested_at") if items else None,
        }


def _item_to_row(user_id: str, item: SportsIntelligenceItem) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "signal_id": item.signal_id,
        "event_id": item.event_id,
        "source_type": item.source_type,
        "title": item.title,
        "summary": item.summary,
        "source_url": item.source_url,
        "author_name": item.author_name,
        "published_at": item.published_at,
        "ingested_at": item.ingested_at,
        "predicted_market": item.predicted_market,
        "predicted_selection": item.predicted_selection,
        "predicted_line": item.predicted_line,
        "predicted_odds": item.predicted_odds,
        "confidence_score": item.confidence_score,
        "sentiment": item.sentiment,
        "key_arguments": item.key_arguments,
        "risk_factors": item.risk_factors,
        "injury_mentions": item.injury_mentions,
        "relevance_score": item.relevance_score,
        "freshness_score": item.freshness_score,
        "content_hash": item.content_hash,
        "duplicate_group_id": item.duplicate_group_id,
        "status": item.status,
        "raw_metadata": {"provider_id": item.provider_id, "source_name": item.source_name},
    }
