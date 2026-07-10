"""Signal outcome logging and performance summaries."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.db.supabase_client import SupabaseClient
from app.services.calibration_service import SIGNAL_TABLES

VALID_OUTCOMES = frozenset({"win", "loss", "scratch", "pending"})
VALID_MODULES = frozenset({"options", "stock", "sports", "parlay"})
USER_ORIGINS = frozenset({"watchlist", "manual", "manual_edit"})
ATLAS_ORIGINS = frozenset({"auto_scan"})
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _origin_from_source(resolution_source: str | None) -> str:
    src = str(resolution_source or "")
    if src in USER_ORIGINS:
        return "user"
    if src == "auto_scan" or src.startswith("auto_"):
        return "atlas"
    return "atlas"


def _merge_pick_origin(existing: str | None, incoming: str) -> str:
    if not existing or existing == incoming:
        return incoming
    if existing == "both" or incoming == "both":
        return "both"
    return "both"


class PerformanceService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def log_outcome(
        self,
        *,
        module: str,
        signal_id: str,
        outcome: str,
        return_pct: float | None = None,
        hold_duration_hours: float | None = None,
        resolution_source: str = "manual",
        signal_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if module not in VALID_MODULES:
            raise ValueError(f"module must be one of: {', '.join(sorted(VALID_MODULES))}")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of: {', '.join(sorted(VALID_OUTCOMES))}")

        signal_id = self._normalize_signal_id(signal_id)
        if not signal_snapshot:
            existing_raw = await self._fetch_outcome_row(module=module, signal_id=signal_id)
            if existing_raw:
                signal_snapshot = existing_raw.get("scoring_snapshot") or {}

        label_source = signal_snapshot or await self._fetch_signal(module, signal_id)
        now = datetime.now(UTC).isoformat()

        # Build snapshot and stamp durable pick_origin (atlas vs user).
        snap: dict[str, Any] = {}
        if label_source and isinstance(label_source.get("scoring_snapshot"), dict):
            snap = dict(label_source["scoring_snapshot"])
        elif isinstance(signal_snapshot, dict):
            # Prefer nested scoring_snapshot; otherwise treat whole payload as snapshot.
            nested = signal_snapshot.get("scoring_snapshot")
            snap = dict(nested) if isinstance(nested, dict) else dict(signal_snapshot)

        incoming_origin = snap.get("pick_origin")
        if incoming_origin not in ("atlas", "user", "both"):
            incoming_origin = _origin_from_source(resolution_source)
        snap["pick_origin"] = incoming_origin
        if resolution_source in USER_ORIGINS:
            snap["user_tracked"] = True
        if resolution_source == "auto_scan" or str(resolution_source).startswith("auto_"):
            snap["atlas_tracked"] = True

        row: dict[str, Any] = {
            "user_id": self.user_id,
            "module": module,
            "signal_id": signal_id,
            "outcome": outcome,
            "return_pct": return_pct,
            "hold_duration_hours": hold_duration_hours,
            "logged_at": now,
            "updated_at": now,
            "resolution_source": resolution_source,
            "resolved_at": now if outcome != "pending" else None,
            "signal_label": self._signal_label(module, label_source, signal_snapshot),
            "opportunity_score": self._score_from_snapshot(label_source, signal_snapshot, "opportunity_score"),
            "confidence_score": self._score_from_snapshot(label_source, signal_snapshot, "confidence_score"),
            "scoring_snapshot": snap,
        }

        existing_raw = await self._fetch_outcome_row(module=module, signal_id=signal_id)
        if existing_raw:
            existing_snap = existing_raw.get("scoring_snapshot") or {}
            if isinstance(existing_snap, dict):
                merged = dict(existing_snap)
                merged.update({k: v for k, v in snap.items() if v is not None})
                prev_origin = existing_snap.get("pick_origin") or _origin_from_source(
                    existing_raw.get("resolution_source")
                )
                merged["pick_origin"] = _merge_pick_origin(str(prev_origin), str(incoming_origin))
                if existing_snap.get("user_tracked") or snap.get("user_tracked"):
                    merged["user_tracked"] = True
                if existing_snap.get("atlas_tracked") or snap.get("atlas_tracked"):
                    merged["atlas_tracked"] = True
                row["scoring_snapshot"] = merged

            # Preserve user/atlas origin when auto-grading — don't erase watchlist identity.
            prev_src = str(existing_raw.get("resolution_source") or "")
            if resolution_source.startswith("auto_") and resolution_source != "auto_scan":
                if prev_src in USER_ORIGINS:
                    # Keep watchlist/manual as origin; grade method lives in snapshot.
                    row["resolution_source"] = prev_src
                    row["scoring_snapshot"]["graded_by"] = resolution_source
                elif prev_src == "auto_scan":
                    row["resolution_source"] = resolution_source

            if not row["signal_label"] and existing_raw.get("signal_label"):
                row["signal_label"] = existing_raw["signal_label"]
            if outcome == "pending" and existing_raw.get("outcome") in ("win", "loss", "scratch"):
                # Never downgrade a graded pick back to pending.
                return self._format_entry(existing_raw)

            update_values = {k: v for k, v in row.items() if k not in ("user_id", "module", "signal_id")}
            # Don't clobber logged_at on updates
            update_values.pop("logged_at", None)
            saved = await self.db.update(
                "signal_performance",
                {"id": f"eq.{existing_raw['id']}", "user_id": f"eq.{self.user_id}"},
                update_values,
            )
            if saved:
                return self._format_entry(saved[0])
            # Row exists but PATCH returned nothing — fall through to upsert.

        try:
            saved = await self.db.upsert(
                "signal_performance",
                [row],
                on_conflict="user_id,module,signal_id",
            )
            if saved:
                return self._format_entry(saved[0])
        except HTTPException as exc:
            detail = str(exc.detail or "")
            if "duplicate" not in detail.lower() and "23505" not in detail:
                raise
            existing_raw = existing_raw or await self._fetch_outcome_row(
                module=module, signal_id=signal_id
            )
            if not existing_raw:
                raise

        if existing_raw:
            update_values = {k: v for k, v in row.items() if k not in ("user_id", "module", "signal_id")}
            update_values.pop("logged_at", None)
            saved = await self.db.update(
                "signal_performance",
                {"id": f"eq.{existing_raw['id']}", "user_id": f"eq.{self.user_id}"},
                update_values,
            )
            if saved:
                return self._format_entry(saved[0])
            refetched = await self._fetch_outcome_row(module=module, signal_id=signal_id)
            if refetched:
                return self._format_entry(refetched)
            raise ValueError("Outcome save failed — row not found after update")

        raise ValueError("Outcome save failed — could not insert or update")

    async def update_outcome(
        self,
        outcome_id: str,
        *,
        outcome: str | None = None,
        return_pct: float | None = None,
        hold_duration_hours: float | None = None,
    ) -> dict[str, Any]:
        rows = await self.db.select(
            "signal_performance",
            filters={"id": f"eq.{outcome_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        if not rows:
            raise ValueError("Outcome not found")

        existing = rows[0]
        new_outcome = outcome if outcome is not None else existing.get("outcome")
        if new_outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of: {', '.join(sorted(VALID_OUTCOMES))}")

        now = datetime.now(UTC).isoformat()
        update_values: dict[str, Any] = {
            "outcome": new_outcome,
            "updated_at": now,
            "resolution_source": "manual_edit",
            "resolved_at": now if new_outcome != "pending" else None,
        }
        if return_pct is not None:
            update_values["return_pct"] = return_pct
        if hold_duration_hours is not None:
            update_values["hold_duration_hours"] = hold_duration_hours

        saved = await self.db.update(
            "signal_performance",
            {"id": f"eq.{outcome_id}", "user_id": f"eq.{self.user_id}"},
            update_values,
        )
        if not saved:
            raise ValueError("Outcome update failed — row not found or not permitted")
        return self._format_entry(saved[0])

    async def register_from_watchlist(self, *, item: dict[str, Any]) -> dict[str, Any] | None:
        """Create a pending performance row when a pick is saved to the watchlist."""
        resolved = self.resolve_watchlist_item(item)
        if not resolved:
            return None
        module, signal_id, snapshot = resolved
        snapshot = dict(snapshot or {})
        snapshot["pick_origin"] = "user"
        snapshot["user_tracked"] = True
        snapshot["watchlist_item_id"] = snapshot.get("watchlist_item_id") or item.get("id")

        existing = await self.get_outcome(module=module, signal_id=signal_id)
        if existing:
            # Promote Atlas-only rows to also count as user picks when saved.
            return await self.log_outcome(
                module=module,
                signal_id=signal_id,
                outcome=str(existing.get("outcome") or "pending"),
                return_pct=existing.get("return_pct"),
                resolution_source="watchlist",
                signal_snapshot=snapshot,
            )

        return await self.log_outcome(
            module=module,
            signal_id=signal_id,
            outcome="pending",
            resolution_source="watchlist",
            signal_snapshot=snapshot,
        )

    @staticmethod
    def resolve_watchlist_item(item: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
        """Map a watchlist row to performance module, signal_id, and snapshot."""
        meta = item.get("metadata") or {}
        item_type = str(item.get("item_type") or "")
        kind = str(meta.get("watchlist_kind") or item_type)

        module_map: dict[str, str] = {
            "sport_bet": "sports",
            "sport_event": "sports",
            "stock_signal": "stock",
            "option_signal": "options",
            "parlay": "parlay",
        }

        module = module_map.get(kind)
        if not module:
            if item_type == "sport_event" or kind == "sport_event":
                if meta.get("legs") or meta.get("parlay_id"):
                    module = "parlay"
                elif meta.get("signal_id") or meta.get("bet_type") or meta.get("selection"):
                    module = "sports"
            elif item_type == "ticker" or kind == "ticker":
                if meta.get("signal_id") and (meta.get("underlying") or meta.get("option_type")):
                    module = "options"
                elif meta.get("signal_id") and (meta.get("ticker") or meta.get("recommendation")):
                    module = "stock"
            elif meta.get("legs") or meta.get("parlay_id"):
                module = "parlay"

        if not module:
            return None

        if module == "parlay":
            signal_id = str(meta.get("parlay_id") or item.get("id") or "")
        elif meta.get("signal_id"):
            signal_id = str(meta["signal_id"])
        elif _UUID_RE.match(str(item.get("symbol") or "")):
            signal_id = str(item.get("symbol"))
        else:
            return None

        if not signal_id:
            return None

        snapshot = {
            **meta,
            "watchlist_item_id": item.get("id"),
            "symbol": item.get("symbol"),
            "label": meta.get("label")
            or meta.get("recommendation")
            or meta.get("selection")
            or meta.get("name")
            or item.get("symbol"),
        }
        return module, PerformanceService._normalize_signal_id(signal_id), snapshot

    async def get_outcome(self, *, module: str, signal_id: str) -> dict[str, Any] | None:
        row = await self._fetch_outcome_row(module=module, signal_id=signal_id)
        return self._format_entry(row) if row else None

    async def _fetch_outcome_row(self, *, module: str, signal_id: str) -> dict[str, Any] | None:
        normalized = self._normalize_signal_id(signal_id)
        rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "module": f"eq.{module}",
                "signal_id": f"eq.{normalized}",
            },
            limit=1,
        )
        return rows[0] if rows else None

    @staticmethod
    def _normalize_signal_id(signal_id: str) -> str:
        sid = signal_id.strip()
        if _UUID_RE.match(sid):
            return sid.lower()
        return sid

    async def get_history(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        module: str | None = None,
        resolved_only: bool = False,
        pending_only: bool = False,
    ) -> dict[str, Any]:
        filters: dict[str, str] = {"user_id": f"eq.{self.user_id}"}
        if module:
            filters["module"] = f"eq.{module}"
        if resolved_only:
            filters["outcome"] = "in.(win,loss,scratch)"
        elif pending_only:
            filters["outcome"] = "eq.pending"

        rows = await self.db.select(
            "signal_performance",
            filters=filters,
            order="logged_at.desc",
            limit=limit,
            offset=offset,
        )
        return {
            "items": [self._format_entry(r) for r in rows],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    async def get_summary(self, *, days: int = 30, module: str | None = None) -> dict[str, Any]:
        since = (datetime.now(UTC) - timedelta(days=max(1, days))).isoformat()
        filters: dict[str, str] = {
            "user_id": f"eq.{self.user_id}",
            "logged_at": f"gte.{since}",
        }
        if module:
            filters["module"] = f"eq.{module}"

        rows = await self.db.select(
            "signal_performance",
            filters=filters,
            order="logged_at.desc",
            limit=1000,
        )
        summary = self._compute_summary(rows, days=days, module=module)
        from app.services.calibration_service import CalibrationService

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments()
        summary["calibration"] = calibration
        summary["confidence_accuracy"] = calibration.get("confidence_accuracy") or {}
        summary["learning_active"] = bool(calibration.get("active"))
        summary["learning_notes"] = calibration.get("learning_notes") or []
        return summary

    async def aggregate_and_store(self, *, days: int = 30) -> dict[str, Any]:
        """Coach-style nightly rollup into performance_summaries."""
        summary = await self.get_summary(days=days)
        period_end = date.today()
        period_start = period_end - timedelta(days=days)
        confidence_accuracy = summary.get("confidence_accuracy") or {}

        for mod in (None, *sorted(VALID_MODULES)):
            mod_rows = summary["by_module"].get(mod or "all", {})
            if mod and mod not in summary["by_module"]:
                continue
            payload = mod_rows if mod else summary
            wins = payload.get("wins", 0)
            losses = payload.get("losses", 0)
            scratches = payload.get("scratches", 0)
            total = wins + losses + scratches
            if total == 0 and mod:
                continue

            await self.db.insert(
                "performance_summaries",
                [
                    {
                        "user_id": self.user_id,
                        "module": mod,
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "total_signals": total,
                        "wins": wins,
                        "losses": losses,
                        "scratches": scratches,
                        "avg_return_pct": payload.get("avg_return_pct"),
                        "avg_loss_pct": payload.get("avg_loss_pct"),
                        "avg_hold_hours": payload.get("avg_hold_hours"),
                        "confidence_accuracy": confidence_accuracy if not mod else {},
                        "strategy_breakdown": summary.get("by_module", {}),
                    }
                ],
            )

        return summary

    async def _fetch_signal(self, module: str, signal_id: str) -> dict[str, Any] | None:
        table = SIGNAL_TABLES.get(module)
        if not table:
            return None
        rows = await self.db.select(
            table,
            filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    @staticmethod
    def _signal_label(
        module: str,
        row: dict[str, Any] | None,
        snapshot: dict[str, Any] | None = None,
    ) -> str | None:
        source = row or snapshot
        if not source:
            return None
        if isinstance(source.get("label"), str):
            return source["label"]
        if module == "sports":
            return f"{source.get('sport')} · {source.get('selection')}"
        if module == "stock":
            return str(source.get("symbol") or source.get("ticker") or source.get("recommendation") or "")
        if module == "options":
            return f"{source.get('underlying')} {source.get('option_type')} {source.get('strike')}"
        if module == "parlay":
            return str(source.get("name") or source.get("title") or source.get("style") or "Parlay")
        return None

    @staticmethod
    def _score_from_snapshot(
        row: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        key: str,
    ) -> float | None:
        for source in (row, snapshot):
            if source and source.get(key) is not None:
                return float(source[key])
        return None

    def _compute_summary(
        self,
        rows: list[dict[str, Any]],
        *,
        days: int,
        module: str | None,
    ) -> dict[str, Any]:
        closed = [r for r in rows if r.get("outcome") in ("win", "loss", "scratch")]
        wins = [r for r in closed if r.get("outcome") == "win"]
        losses = [r for r in closed if r.get("outcome") == "loss"]
        scratches = [r for r in closed if r.get("outcome") == "scratch"]

        win_returns = [float(r["return_pct"]) for r in wins if r.get("return_pct") is not None]
        loss_returns = [float(r["return_pct"]) for r in losses if r.get("return_pct") is not None]
        hold_hours = [
            float(r["hold_duration_hours"])
            for r in closed
            if r.get("hold_duration_hours") is not None
        ]

        decided = len(wins) + len(losses)
        win_rate = round(len(wins) / decided * 100, 1) if decided else None

        by_module: dict[str, Any] = {}
        for mod in VALID_MODULES:
            mod_rows = [r for r in rows if r.get("module") == mod]
            if mod_rows:
                by_module[mod] = self._compute_summary(mod_rows, days=days, module=mod)

        auto_resolved = len(
            [
                r
                for r in rows
                if (
                    str(r.get("resolution_source") or "").startswith("auto_")
                    or (isinstance(r.get("scoring_snapshot"), dict) and r["scoring_snapshot"].get("graded_by"))
                )
                and r.get("outcome") in ("win", "loss", "scratch")
            ]
        )

        atlas_count = user_count = 0
        for r in rows:
            origin = self._pick_origin(r)
            if origin in ("atlas", "both"):
                atlas_count += 1
            if origin in ("user", "both"):
                user_count += 1

        return {
            "days": days,
            "module": module,
            "total_signals": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "scratches": len(scratches),
            "pending": len([r for r in rows if r.get("outcome") == "pending"]),
            "win_rate": win_rate,
            "avg_return_pct": round(sum(win_returns) / len(win_returns), 2) if win_returns else None,
            "avg_loss_pct": round(sum(loss_returns) / len(loss_returns), 2) if loss_returns else None,
            "avg_hold_hours": round(sum(hold_hours) / len(hold_hours), 1) if hold_hours else None,
            "auto_resolved": auto_resolved,
            "atlas_picks": atlas_count,
            "user_picks": user_count,
            "by_module": by_module,
        }

    @staticmethod
    def _pick_origin(row: dict[str, Any]) -> str:
        snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
        origin = snap.get("pick_origin")
        if origin in ("atlas", "user", "both"):
            return str(origin)
        if snap.get("user_tracked") and snap.get("atlas_tracked"):
            return "both"
        if snap.get("user_tracked") or snap.get("watchlist_item_id"):
            return "user"
        return _origin_from_source(row.get("resolution_source"))

    @staticmethod
    def _format_entry(row: dict[str, Any]) -> dict[str, Any]:
        snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
        origin = PerformanceService._pick_origin(row)
        return {
            "id": row["id"],
            "module": row["module"],
            "signal_id": row["signal_id"],
            "outcome": row["outcome"],
            "return_pct": row.get("return_pct"),
            "hold_duration_hours": row.get("hold_duration_hours"),
            "logged_at": row.get("logged_at"),
            "created_at": row.get("created_at"),
            "resolution_source": row.get("resolution_source"),
            "signal_label": row.get("signal_label"),
            "opportunity_score": row.get("opportunity_score"),
            "confidence_score": row.get("confidence_score"),
            "pick_origin": origin,
            "graded_by": snap.get("graded_by"),
        }
