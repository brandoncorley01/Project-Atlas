"""Signal outcome logging and performance summaries."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.services.calibration_service import SIGNAL_TABLES

VALID_OUTCOMES = frozenset({"win", "loss", "scratch", "pending"})
VALID_MODULES = frozenset({"options", "stock", "sports", "parlay"})
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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
            "scoring_snapshot": (label_source or {}).get("scoring_snapshot")
            if label_source and label_source.get("scoring_snapshot")
            else (signal_snapshot or {}),
        }

        existing_raw = await self._fetch_outcome_row(module=module, signal_id=signal_id)
        if existing_raw:
            if not row["signal_label"] and existing_raw.get("signal_label"):
                row["signal_label"] = existing_raw["signal_label"]
            if not row["scoring_snapshot"] and existing_raw.get("scoring_snapshot"):
                row["scoring_snapshot"] = existing_raw["scoring_snapshot"]
            update_values = {k: v for k, v in row.items() if k not in ("user_id", "module", "signal_id")}
            saved = await self.db.update(
                "signal_performance",
                {"id": f"eq.{existing_raw['id']}", "user_id": f"eq.{self.user_id}"},
                update_values,
            )
            return self._format_entry(saved[0])

        saved = await self.db.insert("signal_performance", [row])
        return self._format_entry(saved[0])

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
        meta = item.get("metadata") or {}
        kind = meta.get("watchlist_kind") or item.get("item_type")

        module_map: dict[str, str] = {
            "sport_bet": "sports",
            "sport_event": "sports",
            "stock_signal": "stock",
            "option_signal": "options",
            "parlay": "parlay",
        }
        module = module_map.get(str(kind))
        if not module:
            return None

        signal_id: str | None = None
        if kind == "parlay" or item.get("item_type") == "parlay":
            signal_id = str(meta.get("parlay_id") or item.get("id") or "")
        elif meta.get("signal_id"):
            signal_id = str(meta["signal_id"])
        else:
            signal_id = str(item.get("id") or "")

        if not signal_id:
            return None

        signal_id = self._normalize_signal_id(signal_id)
        existing = await self.get_outcome(module=module, signal_id=signal_id)
        if existing:
            return existing

        snapshot = {
            **meta,
            "watchlist_item_id": item.get("id"),
            "symbol": item.get("symbol"),
        }
        return await self.log_outcome(
            module=module,
            signal_id=signal_id,
            outcome="pending",
            resolution_source="watchlist",
            signal_snapshot=snapshot,
        )

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
            limit=500,
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
                if str(r.get("resolution_source") or "").startswith("auto_")
                and r.get("outcome") in ("win", "loss", "scratch")
            ]
        )

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
            "by_module": by_module,
        }

    @staticmethod
    def _format_entry(row: dict[str, Any]) -> dict[str, Any]:
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
        }
