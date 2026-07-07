"""In-app alerts — signal thresholds, news, and read state."""

from __future__ import annotations

import logging
from typing import Any

from app.db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

MODULE_ALERT_TYPES = {
    "options": "options_signal",
    "stock": "stock_signal",
    "sports": "sports_signal",
    "parlay": "parlay_opportunity",
}

DEFAULT_SCORE_THRESHOLD = 72.0


class AlertService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def list_alerts(
        self,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        filters: dict[str, str] = {"user_id": f"eq.{self.user_id}"}
        if unread_only:
            filters["read"] = "eq.false"
        rows = await self.db.select(
            "alerts",
            filters=filters,
            order="created_at.desc",
            limit=limit,
            offset=offset,
        )
        items = [self._format_alert(row) for row in rows]
        unread = await self.unread_count() if not unread_only else len(items)
        return {
            "items": items,
            "total": len(items),
            "unread_count": unread,
            "unread_only": unread_only,
            "limit": limit,
            "offset": offset,
        }

    async def unread_count(self) -> int:
        rows = await self.db.select(
            "alerts",
            filters={"user_id": f"eq.{self.user_id}", "read": "eq.false"},
            select="id",
            limit=1000,
        )
        return len(rows)

    async def mark_read(self, alert_id: str) -> dict[str, Any] | None:
        rows = await self.db.update(
            "alerts",
            {"id": f"eq.{alert_id}", "user_id": f"eq.{self.user_id}"},
            {"read": True},
        )
        return self._format_alert(rows[0]) if rows else None

    async def mark_all_read(self) -> int:
        rows = await self.db.select(
            "alerts",
            filters={"user_id": f"eq.{self.user_id}", "read": "eq.false"},
            select="id",
            limit=500,
        )
        if not rows:
            return 0
        for row in rows:
            await self.db.update(
                "alerts",
                {"id": f"eq.{row['id']}"},
                {"read": True},
            )
        return len(rows)

    async def create_alert(
        self,
        *,
        alert_type: str,
        title: str,
        message: str,
        module: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        if reference_id and module:
            dup = await self.db.select(
                "alerts",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "module": f"eq.{module}",
                    "reference_id": f"eq.{reference_id}",
                    "alert_type": f"eq.{alert_type}",
                },
                limit=1,
            )
            if dup:
                return self._format_alert(dup[0])

        row = {
            "user_id": self.user_id,
            "alert_type": alert_type,
            "title": title,
            "message": message,
            "read": False,
        }
        if module:
            row["module"] = module
        if reference_id:
            row["reference_id"] = reference_id

        saved = await self.db.insert("alerts", [row])
        return self._format_alert(saved[0])

    async def notify_high_score_signals(
        self,
        module: str,
        signals: list[dict[str, Any]],
        *,
        threshold: float = DEFAULT_SCORE_THRESHOLD,
        title_fn=None,
        message_fn=None,
    ) -> int:
        """Create alerts for signals above threshold (skips duplicates)."""
        alert_type = MODULE_ALERT_TYPES.get(module, "options_signal")
        created = 0
        for sig in signals:
            score = float(sig.get("opportunity_score") or 0)
            if score < threshold:
                continue
            sig_id = str(sig.get("id") or "")
            if not sig_id:
                continue
            title = (
                title_fn(sig)
                if title_fn
                else f"High-score {module} signal ({score:.0f}/100)"
            )
            message = (
                message_fn(sig)
                if message_fn
                else str(sig.get("recommendation") or sig.get("explanation") or title)[:500]
            )
            try:
                await self.create_alert(
                    alert_type=alert_type,
                    title=title,
                    message=message,
                    module=module,
                    reference_id=sig_id,
                )
                created += 1
            except Exception as exc:
                logger.info("Alert skip %s: %s", sig_id, exc)
        return created

    @staticmethod
    def _format_alert(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "alert_type": row["alert_type"],
            "title": row["title"],
            "message": row["message"],
            "module": row.get("module"),
            "reference_id": row.get("reference_id"),
            "read": bool(row.get("read")),
            "created_at": row.get("created_at"),
        }
