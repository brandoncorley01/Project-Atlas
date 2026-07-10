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
PARLAY_MODULE = "parlay"


class SignalRegistryService:
    """Ensures every ranked pick enters the learning loop automatically."""

    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def register_batch(self, module: str, rows: list[dict[str, Any]]) -> dict[str, int]:
        """Register a batch of freshly saved signals (idempotent)."""
        if module not in MODULES and module != PARLAY_MODULE:
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
        """Register signals missing from signal_performance (scans, parlays, watchlist)."""
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
                sid = PerformanceService._normalize_signal_id(str(row.get("id") or ""))
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

        parlay_stats = await self._backfill_parlays(tracked, limit=limit_per_module)
        totals["by_module"][PARLAY_MODULE] = parlay_stats
        totals["registered"] += parlay_stats["registered"]
        totals["skipped"] += parlay_stats["skipped"]

        watchlist_stats = await self._backfill_watchlist(tracked, limit=limit_per_module * 2)
        totals["by_module"]["watchlist"] = watchlist_stats
        totals["registered"] += watchlist_stats["registered"]
        totals["skipped"] += watchlist_stats["skipped"]

        return totals

    async def _backfill_parlays(
        self, tracked: set[tuple[str, str]], *, limit: int
    ) -> dict[str, int]:
        registered = 0
        skipped = 0
        try:
            rows = await self.db.select(
                "parlays",
                filters={"user_id": f"eq.{self.user_id}"},
                order="created_at.desc",
                limit=limit,
            )
        except Exception as exc:
            logger.warning("Backfill parlays: %s", exc)
            return {"registered": 0, "skipped": 0, "error": str(exc)}

        for row in rows:
            sid = PerformanceService._normalize_signal_id(str(row.get("id") or ""))
            if not sid or (PARLAY_MODULE, sid) in tracked:
                skipped += 1
                continue
            try:
                existing = await self.performance.get_outcome(module=PARLAY_MODULE, signal_id=sid)
                if existing:
                    skipped += 1
                    tracked.add((PARLAY_MODULE, sid))
                    continue
                await self.performance.log_outcome(
                    module=PARLAY_MODULE,
                    signal_id=sid,
                    outcome="pending",
                    resolution_source=TRACKING_SOURCE,
                    signal_snapshot=row,
                )
                registered += 1
                tracked.add((PARLAY_MODULE, sid))
            except Exception as exc:
                logger.warning("Backfill parlay %s: %s", sid[:8], exc)
                skipped += 1
        return {"registered": registered, "skipped": skipped}

    async def _backfill_watchlist(
        self, tracked: set[tuple[str, str]], *, limit: int
    ) -> dict[str, int]:
        registered = 0
        skipped = 0
        try:
            rows = await self.db.select(
                "watchlist_items",
                filters={"user_id": f"eq.{self.user_id}"},
                order="created_at.desc",
                limit=limit,
            )
        except Exception as exc:
            logger.warning("Backfill watchlist: %s", exc)
            return {"registered": 0, "skipped": 0, "error": str(exc)}

        for row in rows:
            item = {
                "id": row.get("id"),
                "item_type": row.get("item_type"),
                "symbol": row.get("symbol"),
                "metadata": row.get("metadata") or {},
            }
            try:
                before = await self._tracking_key_for_item(item)
                if not before:
                    skipped += 1
                    continue
                mod, sid = before
                if (mod, sid) in tracked:
                    skipped += 1
                    continue
                result = await self.performance.register_from_watchlist(item=item)
                if result:
                    registered += 1
                    tracked.add((mod, sid))
                else:
                    skipped += 1
            except Exception as exc:
                logger.warning("Backfill watchlist item %s: %s", row.get("id"), exc)
                skipped += 1
        return {"registered": registered, "skipped": skipped}

    async def _tracking_key_for_item(self, item: dict[str, Any]) -> tuple[str, str] | None:
        meta = item.get("metadata") or {}
        kind = meta.get("watchlist_kind") or item.get("item_type")

        module_map: dict[str, str] = {
            "sport_bet": "sports",
            "sport_event": "sports",
            "stock_signal": "stock",
            "option_signal": "options",
            "parlay": PARLAY_MODULE,
        }
        module = module_map.get(str(kind))
        if not module:
            if meta.get("signal_id") and meta.get("underlying"):
                module = "options"
            elif meta.get("signal_id") and meta.get("ticker"):
                module = "stock"
            elif meta.get("signal_id") or meta.get("bet_type"):
                module = "sports"
            elif meta.get("legs"):
                module = PARLAY_MODULE
            else:
                return None

        if kind == "parlay" or item.get("item_type") == "parlay" or meta.get("legs"):
            signal_id = str(meta.get("parlay_id") or item.get("id") or "")
        elif meta.get("signal_id"):
            signal_id = str(meta["signal_id"])
        else:
            signal_id = str(item.get("id") or "")

        if not signal_id:
            return None
        return module, PerformanceService._normalize_signal_id(signal_id)

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
        signal_id = PerformanceService._normalize_signal_id(signal_id)
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
            (
                str(r.get("module") or ""),
                PerformanceService._normalize_signal_id(str(r.get("signal_id") or "")),
            )
            for r in rows
            if r.get("module") and r.get("signal_id")
        }
