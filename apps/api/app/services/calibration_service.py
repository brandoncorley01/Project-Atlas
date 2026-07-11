"""Learn from logged pick outcomes — tighten thresholds when edge underperforms."""

from __future__ import annotations

from typing import Any

from app.db.supabase_client import SupabaseClient

MIN_SAMPLES = 8
CONFIDENCE_BUCKETS = (
    (0, 60, "50-60"),
    (60, 70, "60-70"),
    (70, 80, "70-80"),
    (80, 90, "80-90"),
    (90, 101, "90+"),
)

SIGNAL_TABLES: dict[str, str] = {
    "options": "options_signals",
    "stock": "stock_signals",
    "sports": "sports_signals",
    "parlay": "parlays",
}


class CalibrationService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def get_adjustments(self, *, lookback: int = 120) -> dict[str, Any]:
        """User-specific scoring tweaks derived from closed picks."""
        rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "outcome": "in.(win,loss,scratch)",
            },
            order="logged_at.desc",
            limit=max(lookback, MIN_SAMPLES * 2),
        )
        if len(rows) < MIN_SAMPLES:
            return self._defaults(sample_count=len(rows))

        by_module: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            mod = str(row.get("module") or "")
            by_module.setdefault(mod, []).append(row)

        sports = self._sports_adjustments(by_module.get("sports") or [])
        options = self._options_adjustments(by_module.get("options") or [])
        stock = self._stock_adjustments(by_module.get("stock") or [])
        confidence_accuracy = self._confidence_accuracy(rows)

        notes: list[str] = []
        if sports.get("note"):
            notes.append(sports["note"])
        if options.get("note"):
            notes.append(options["note"])
        if stock.get("note"):
            notes.append(stock["note"])

        return {
            "sample_count": len(rows),
            "sports_min_edge_pct": sports["min_edge_pct"],
            "sports_min_opportunity": sports["min_opportunity"],
            "sports_confidence_dampen": sports["confidence_dampen"],
            "options_min_profit_probability": options["min_profit_probability"],
            "options_min_opportunity": options["min_opportunity"],
            "stock_min_opportunity": stock["min_opportunity"],
            "confidence_accuracy": confidence_accuracy,
            "learning_notes": notes,
            "active": len(rows) >= MIN_SAMPLES,
        }

    @staticmethod
    def _defaults(*, sample_count: int = 0) -> dict[str, Any]:
        return {
            "sample_count": sample_count,
            "sports_min_edge_pct": 0.6,
            "sports_min_opportunity": 28.0,
            "sports_confidence_dampen": 0.0,
            "options_min_profit_probability": 52.0,
            "options_min_opportunity": 45.0,
            "stock_min_opportunity": 35.0,
            "confidence_accuracy": {},
            "learning_notes": [],
            "active": False,
        }

    def _sports_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_edge = 0.6
        min_opp = 28.0
        dampen = 0.0
        note: str | None = None

        low_edge = []
        for row in rows:
            snap = row.get("scoring_snapshot") or {}
            edge = snap.get("edge_pct")
            if edge is None:
                edge = (row.get("line_movement") or {}).get("edge_pct") if isinstance(row.get("line_movement"), dict) else None
            if edge is not None and float(edge) < 2.0:
                low_edge.append(row)

        if len(low_edge) >= 5:
            wr = self._win_rate(low_edge)
            if wr is not None and wr < 48.0:
                min_edge = 1.0
                min_opp = 32.0
                note = f"Sports: low-edge picks won {wr:.0f}% — raised edge bar to {min_edge}%"

        mid_conf = [r for r in rows if self._confidence(r) is not None and 70 <= self._confidence(r) < 85]
        if len(mid_conf) >= 5:
            wr = self._win_rate(mid_conf)
            if wr is not None and wr < 50.0:
                dampen = 5.0
                if not note:
                    note = f"Sports: 70–85 confidence bucket won {wr:.0f}% — scores adjusted"

        return {
            "min_edge_pct": min_edge,
            "min_opportunity": min_opp,
            "confidence_dampen": dampen,
            "note": note,
        }

    def _options_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_prob = 52.0
        min_opp = 45.0
        note: str | None = None

        mid_prob = []
        for row in rows:
            snap = row.get("scoring_snapshot") or {}
            prob = snap.get("profit_probability")
            if prob is not None and 52 <= float(prob) < 62:
                mid_prob.append(row)

        if len(mid_prob) >= 5:
            wr = self._win_rate(mid_prob)
            if wr is not None and wr < 45.0:
                min_prob = 58.0
                min_opp = 48.0
                note = f"Options: 52–62% prob picks won {wr:.0f}% — raised minimum to {min_prob:.0f}%"

        return {
            "min_profit_probability": min_prob,
            "min_opportunity": min_opp,
            "note": note,
        }

    def _stock_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_opp = 35.0
        note: str | None = None

        low_opp = [r for r in rows if self._opportunity(r) is not None and self._opportunity(r) < 42]
        if len(low_opp) >= 5:
            wr = self._win_rate(low_opp)
            if wr is not None and wr < 45.0:
                min_opp = 40.0
                note = f"Stocks: sub-42 opportunity picks won {wr:.0f}% — minimum raised to {min_opp:.0f}"

        return {"min_opportunity": min_opp, "note": note}

    def _confidence_accuracy(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {label: [] for _, _, label in CONFIDENCE_BUCKETS}
        for row in rows:
            conf = self._confidence(row)
            if conf is None:
                continue
            for low, high, label in CONFIDENCE_BUCKETS:
                if low <= conf < high:
                    buckets[label].append(row)
                    break

        out: dict[str, dict[str, Any]] = {}
        for label, bucket_rows in buckets.items():
            if not bucket_rows:
                continue
            wr = self._win_rate(bucket_rows)
            if wr is None:
                continue
            out[label] = {
                "count": len(bucket_rows),
                "win_rate": wr,
                "expected_mid": (int(label.split("-")[0]) + int(label.split("-")[1].replace("+", ""))) / 2
                if "+" not in label
                else 92,
            }
        return out

    @staticmethod
    def _win_rate(rows: list[dict[str, Any]]) -> float | None:
        decided = [r for r in rows if r.get("outcome") in ("win", "loss")]
        if not decided:
            return None
        wins = sum(1 for r in decided if r.get("outcome") == "win")
        return round(wins / len(decided) * 100, 1)

    @staticmethod
    def _confidence(row: dict[str, Any]) -> float | None:
        val = row.get("confidence_score")
        if val is not None:
            return float(val)
        snap = row.get("scoring_snapshot") or {}
        if snap.get("confidence_score") is not None:
            return float(snap["confidence_score"])
        return None

    @staticmethod
    def _opportunity(row: dict[str, Any]) -> float | None:
        val = row.get("opportunity_score")
        if val is not None:
            return float(val)
        snap = row.get("scoring_snapshot") or {}
        if snap.get("opportunity_score") is not None:
            return float(snap["opportunity_score"])
        return None
