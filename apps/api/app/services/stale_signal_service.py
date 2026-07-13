"""Mark expired signals in the database when events pass or data ages out."""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.db.supabase_client import SupabaseClient
from app.services.freshness import (
    is_options_fresh,
    is_parlay_fresh,
    is_sports_listable,
    is_stock_fresh,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50

_EXPIRE_SELECT: dict[str, str] = {
    "sports_signals": "id,event_start,bet_type,scoring_snapshot,line_movement",
    "stock_signals": "id,data_as_of",
    "options_signals": "id,expiration,data_as_of",
    "parlays": "id,data_as_of",
}


class StaleSignalService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def expire_all(self, *, include_sports: bool = True) -> dict[str, int]:
        """Move stale active rows to status=expired.

        Sports: kickoff already passed (concluded/in-progress) leave the live board.
        """
        counts: dict[str, int] = {}
        if include_sports:
            counts["sports"] = await self._expire_table("sports_signals", is_sports_listable)
        counts["stocks"] = await self._expire_table("stock_signals", is_stock_fresh)
        counts["options"] = await self._expire_table("options_signals", is_options_fresh)
        counts["parlays"] = await self._expire_table("parlays", is_parlay_fresh)
        return counts

    async def expire_concluded_sports(self) -> int:
        """Expire sports picks whose event has started or finished."""
        return await self._expire_table("sports_signals", is_sports_listable)

    async def _expire_table(
        self,
        table: str,
        is_fresh: Callable[[dict[str, Any]], bool],
    ) -> int:
        try:
            rows = await self.db.select(
                table,
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "status": "eq.active",
                },
                select=_EXPIRE_SELECT.get(table, "id"),
                limit=500,
            )
        except Exception as exc:
            logger.warning("Expire stale %s: %s", table, exc)
            return 0

        stale_ids = [row["id"] for row in rows if row.get("id") and not is_fresh(row)]
        if not stale_ids:
            return 0

        expired = 0
        for start in range(0, len(stale_ids), _BATCH_SIZE):
            chunk = stale_ids[start : start + _BATCH_SIZE]
            try:
                await self.db.update(
                    table,
                    {
                        "id": f"in.({','.join(chunk)})",
                        "user_id": f"eq.{self.user_id}",
                    },
                    {"status": "expired"},
                )
                expired += len(chunk)
            except Exception as exc:
                logger.info("Batch expire %s (%d ids): %s", table, len(chunk), exc)
        return expired
