"""Watchlist CRUD — tickers, teams, and sport events to track."""

from __future__ import annotations

from typing import Any

from app.db.supabase_client import SupabaseClient

VALID_ITEM_TYPES = frozenset({
    "ticker",
    "sport_event",
    "team",
    "sport_bet",
    "parlay",
    "stock_signal",
    "option_signal",
})


class WatchlistService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

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
        if item_type == "ticker":
            sym = sym.upper()
        if item_type not in VALID_ITEM_TYPES:
            raise ValueError(f"item_type must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}")

        wl = await self._ensure_default_watchlist()
        existing = await self.db.select(
            "watchlist_items",
            filters={
                "watchlist_id": f"eq.{wl['id']}",
                "item_type": f"eq.{item_type}",
                "symbol": f"eq.{sym}",
            },
            limit=1,
        )
        if existing:
            return self._format_item(existing[0])

        saved = await self.db.insert(
            "watchlist_items",
            [
                {
                    "watchlist_id": wl["id"],
                    "user_id": self.user_id,
                    "item_type": item_type,
                    "symbol": sym,
                    "metadata": metadata or {},
                }
            ],
        )
        return self._format_item(saved[0])

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
