"""Watchlist CRUD — tickers, teams, and sport events to track."""

from __future__ import annotations

from typing import Any

from app.db.supabase_client import SupabaseClient
from app.services.performance_service import PerformanceService

VALID_ITEM_TYPES = frozenset({
    "ticker",
    "sport_event",
    "team",
    "sport_bet",
    "parlay",
    "stock_signal",
    "option_signal",
})

TRACKABLE_KINDS = frozenset({"sport_bet", "stock_signal", "option_signal", "parlay"})


class WatchlistService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def _ensure_default_watchlist(self) -> dict[str, Any]:
        rows = await self.db.select(
            "watchlists",
            filters={"user_id": f"eq.{self.user_id}", "name": "eq.Default"},
            limit=1,
        )
        if rows:
            return rows[0]
        created = await self.db.insert(
            "watchlists",
            [{"user_id": self.user_id, "name": "Default"}],
        )
        return created[0]

    async def get_watchlist(self) -> dict[str, Any]:
        wl = await self._ensure_default_watchlist()
        items = await self.db.select(
            "watchlist_items",
            filters={"watchlist_id": f"eq.{wl['id']}"},
            order="created_at.desc",
        )
        return {
            "id": wl["id"],
            "name": wl["name"],
            "items": [self._format_item(row) for row in items],
        }

    async def add_item(
        self,
        *,
        symbol: str,
        item_type: str = "ticker",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sym = symbol.strip()
        if not sym:
            raise ValueError("symbol is required")

        meta = dict(metadata or {})
        storage_type = self._storage_item_type(item_type, meta)
        if storage_type == "ticker":
            sym = sym.upper()
        if storage_type not in VALID_ITEM_TYPES:
            raise ValueError(f"item_type must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}")

        wl = await self._ensure_default_watchlist()
        existing = await self.db.select(
            "watchlist_items",
            filters={
                "watchlist_id": f"eq.{wl['id']}",
                "item_type": f"eq.{storage_type}",
                "symbol": f"eq.{sym}",
            },
            limit=1,
        )
        if existing:
            row = existing[0]
            if meta:
                updated = await self.db.update(
                    "watchlist_items",
                    {"id": f"eq.{row['id']}"},
                    {"metadata": meta},
                )
                if updated:
                    row = updated[0]
            item = self._format_item(row)
        else:
            saved = await self.db.insert(
                "watchlist_items",
                [
                    {
                        "watchlist_id": wl["id"],
                        "user_id": self.user_id,
                        "item_type": storage_type,
                        "symbol": sym,
                        "metadata": meta,
                    }
                ],
            )
            item = self._format_item(saved[0])

        tracking = await self._register_tracking(item)
        if tracking:
            item["tracking"] = tracking
        return item

    @staticmethod
    def _storage_item_type(item_type: str, metadata: dict[str, Any]) -> str:
        # Frontend may map to legacy DB types (sport_event/ticker); watchlist_kind in metadata
        # drives UI tabs and performance routing.
        _ = metadata
        return item_type

    async def _register_tracking(self, item: dict[str, Any]) -> dict[str, Any] | None:
        kind = item.get("metadata", {}).get("watchlist_kind") or item.get("item_type")
        if kind not in TRACKABLE_KINDS and item.get("item_type") not in TRACKABLE_KINDS:
            meta = item.get("metadata") or {}
            if not (meta.get("signal_id") or meta.get("legs")):
                return None
        try:
            return await self.performance.register_from_watchlist(item=item)
        except Exception:
            return None

    async def remove_item(self, item_id: str) -> bool:
        wl = await self._ensure_default_watchlist()
        rows = await self.db.select(
            "watchlist_items",
            filters={"id": f"eq.{item_id}", "watchlist_id": f"eq.{wl['id']}"},
            limit=1,
        )
        if not rows:
            return False
        await self.db.delete("watchlist_items", {"id": f"eq.{item_id}"})
        return True

    @staticmethod
    def _format_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "item_type": row["item_type"],
            "symbol": row["symbol"],
            "metadata": row.get("metadata") or {},
            "created_at": row.get("created_at"),
        }
