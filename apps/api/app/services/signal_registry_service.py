"""Auto-register every Atlas signal for tracking — no watchlist or manual log required."""

from __future__ import annotations

import logging
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.services.calibration_service import SIGNAL_TABLES
from app.services.performance_service import PerformanceService

logger = logging.getLogger(__name__)

TRACKING_SOURCE = "auto_scan"
MODULES = ("options", "stock", "sports")


class SignalRegistryService:
    """Ensures every ranked pick enters the learning loop automatically."""

    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def register_batch(self, module: str, rows: list[dict[str, Any]]) -> dict[str, int]:
        """Register a batch of freshly saved signals (idempotent)."""
        if module not in MODULES:
            return {"registered": 0, "skipped": 0}

        registered = 0
        skipped = 0
        for row in rows:
            signal_id = str(row.get("id") or "")
            if not signal_id:
                skipped += 1
                continue
            try:
                created = await self._register_one(module, signal_id, row)
                if created:
                    registered += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.warning("Register %s %s: %s", module, signal_id[:8], exc)
                skipped += 1
        return {"registered": registered, "skipped": skipped}

    async def backfill_all(self, *, limit_per_module: int = 120) -> dict[str, Any]:
        """Register any signals missing from signal_performance (historical catch-up)."""
        totals = {"registered": 0, "skipped": 0, "by_module": {}}
        tracked = await self._tracked_ids()

        for module in MODULES:
            table = SIGNAL_TABLES[module]
            try:
                rows = await self.db.select(
                    table,
                    filters={"user_id": f"eq.{self.user_id}"},
                    order="data_as_of.desc" if module != "sports" else "event_start.desc",
                    limit=limit_per_module,
                )
            except Exception as exc:
                logger.warning("Backfill select %s: %s", table, exc)
                totals["by_module"][module] = {"registered": 0, "skipped": 0, "error": str(exc)}
                continue

            mod_registered = 0
            mod_skipped = 0
            for row in rows:
                sid = str(row.get("id") or "")
                if not sid or (module, sid) in tracked:
                    mod_skipped += 1
                    continue
                try:
                    if await self._register_one(module, sid, row):
                        mod_registered += 1
                        tracked.add((module, sid))
                    else:
                        mod_skipped += 1
                except Exception as exc:
                    logger.warning("Backfill register %s %s: %s", module, sid[:8], exc)
                    mod_skipped += 1

            totals["by_module"][module] = {"registered": mod_registered, "skipped": mod_skipped}
            totals["registered"] += mod_registered
            totals["skipped"] += mod_skipped

        return totals

    async def tracking_stats(self) -> dict[str, Any]:
        """Counts for auto-tracked vs manually logged picks."""
        rows = await self.db.select(
            "signal_performance",
            filters={"user_id": f"eq.{self.user_id}"},
            limit=1000,
        )
        auto_pending = auto_resolved = manual = watchlist = 0
        by_module: dict[str, dict[str, int]] = {}

        for row in rows:
            mod = str(row.get("module") or "")
            src = str(row.get("resolution_source") or "")
            outcome = str(row.get("outcome") or "")
            bucket = by_module.setdefault(mod, {"total": 0, "pending": 0, "resolved": 0})
            bucket["total"] += 1
            if outcome in ("win", "loss", "scratch"):
                bucket["resolved"] += 1
            else:
                bucket["pending"] += 1

            if src == TRACKING_SOURCE:
                if outcome in ("win", "loss", "scratch"):
                    auto_resolved += 1
                else:
                    auto_pending += 1
            elif src.startswith("auto_"):
                if outcome in ("win", "loss", "scratch"):
                    auto_resolved += 1
                else:
                    auto_pending += 1
            elif src == "watchlist":
                watchlist += 1
            elif src in ("manual", ""):
                manual += 1

        return {
            "total_tracked": len(rows),
            "auto_pending": auto_pending,
            "auto_resolved": auto_resolved,
            "manual_logged": manual,
            "watchlist_tracked": watchlist,
            "by_module": by_module,
        }

    async def _register_one(self, module: str, signal_id: str, row: dict[str, Any]) -> bool:
        existing = await self.performance.get_outcome(module=module, signal_id=signal_id)
        if existing:
            return False
        await self.performance.log_outcome(
            module=module,
            signal_id=signal_id,
            outcome="pending",
            resolution_source=TRACKING_SOURCE,
            signal_snapshot=row,
        )
        return True

    async def _tracked_ids(self) -> set[tuple[str, str]]:
        rows = await self.db.select(
            "signal_performance",
            filters={"user_id": f"eq.{self.user_id}"},
            limit=2000,
        )
        return {
            (str(r.get("module") or ""), str(r.get("signal_id") or ""))
            for r in rows
            if r.get("module") and r.get("signal_id")
        }
