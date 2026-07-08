"""AI market intelligence from Atlas's full auto-tracked pick corpus."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_INTELLIGENCE_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}

_INTELLIGENCE_SYSTEM = """You are Atlas's market intelligence engine.
Analyze logged pick outcomes to find patterns, calibration gaps, and actionable edge insights.
Never invent statistics — only interpret the data provided.
Focus on: which modules/sports/bet-types work, where confidence is miscalibrated, and what Atlas should weight more or less.
Tone: analytical, concise, forward-looking. This powers a competitive trading/betting intelligence app."""


def _today_key() -> str:
    return date.today().isoformat()


def _template_intelligence(stats: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = stats.get("total_tracked") or 0
    resolved = stats.get("auto_resolved", 0) + stats.get("manual_logged", 0)
    win_rate = stats.get("win_rate")

    patterns: list[str] = []
    by_mod = stats.get("by_module") or {}
    for mod, bucket in by_mod.items():
        if isinstance(bucket, dict) and bucket.get("resolved", 0) >= 3:
            patterns.append(f"{mod}: {bucket['resolved']} graded picks in tracking pool.")

    if win_rate is not None:
        patterns.append(f"Overall win rate across tracked picks: {win_rate}%.")

    learning = stats.get("learning_notes") or []
    if learning:
        patterns.append(learning[0])

    if not patterns:
        patterns.append(
            "Atlas is building your market profile — every scan auto-registers picks for outcome tracking."
        )

    return {
        "headline": "Market intelligence" if total > 0 else "Intelligence warming up",
        "summary": (
            f"Tracking {total} Atlas picks ({resolved} with outcomes). "
            "Every scan registers signals automatically — no watchlist required."
            if total > 0
            else "Run scans to start auto-tracking. Atlas learns from every ranked pick, not just saved ones."
        ),
        "patterns": patterns[:5],
        "edge_notes": [
            "Log Win/Loss on picks you actually take — manual grades sharpen calibration faster.",
            "Sports, stocks, and options all auto-grade when events expire.",
        ],
        "regime": None,
        "sample_count": len(samples),
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "template",
        "model": None,
    }


class MarketIntelligenceService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def get_resolved_samples(self, *, limit: int = 80) -> list[dict[str, Any]]:
        rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "outcome": "in.(win,loss,scratch)",
            },
            order="logged_at.desc",
            limit=limit,
        )
        return [
            {
                "module": r.get("module"),
                "outcome": r.get("outcome"),
                "return_pct": r.get("return_pct"),
                "confidence": r.get("confidence_score"),
                "opportunity": r.get("opportunity_score"),
                "source": r.get("resolution_source"),
                "label": r.get("signal_label"),
            }
            for r in rows
        ]

    async def generate(
        self,
        *,
        tracking_stats: dict[str, Any],
        perf_summary: dict[str, Any],
        calibration: dict[str, Any],
        refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = f"{self.user_id}:{_today_key()}"
        if not refresh and cache_key in _INTELLIGENCE_CACHE:
            return dict(_INTELLIGENCE_CACHE[cache_key][1])

        samples = await self.get_resolved_samples()
        stats = {
            **tracking_stats,
            "win_rate": perf_summary.get("win_rate"),
            "learning_notes": calibration.get("learning_notes") or perf_summary.get("learning_notes"),
            "confidence_accuracy": calibration.get("confidence_accuracy") or perf_summary.get("confidence_accuracy"),
            "calibration_active": calibration.get("active"),
        }

        base = _template_intelligence(stats, samples)
        if not llm_service.is_configured() or len(samples) < 3:
            _INTELLIGENCE_CACHE[cache_key] = (_today_key(), base)
            return dict(base)

        payload = {
            "tracking": stats,
            "recent_outcomes": samples[:40],
            "by_module_performance": perf_summary.get("by_module"),
            "calibration": {
                "active": calibration.get("active"),
                "sample_count": calibration.get("sample_count"),
                "sports_min_edge_pct": calibration.get("sports_min_edge_pct"),
                "options_min_profit_probability": calibration.get("options_min_profit_probability"),
                "stock_min_opportunity": calibration.get("stock_min_opportunity"),
            },
        }

        llm_result = await llm_service.complete_json(
            system=_INTELLIGENCE_SYSTEM,
            user=(
                "Return JSON with keys: headline (string), summary (2-3 sentences), "
                "patterns (array of 3-5 insight strings), edge_notes (array of 2-3 actionable strings), "
                "regime (string or null — e.g. 'choppy markets', 'sports edge strong').\n\n"
                f"DATA:\n{payload}"
            ),
            max_tokens=900,
        )

        if llm_result:
            result = {
                "headline": str(llm_result.get("headline") or base["headline"])[:120],
                "summary": str(llm_result.get("summary") or base["summary"])[:800],
                "patterns": [str(p)[:200] for p in (llm_result.get("patterns") or base["patterns"])[:5]],
                "edge_notes": [str(e)[:200] for e in (llm_result.get("edge_notes") or base["edge_notes"])[:3]],
                "regime": llm_result.get("regime"),
                "sample_count": len(samples),
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "openai",
                "model": llm_service.model,
            }
        else:
            result = base

        _INTELLIGENCE_CACHE[cache_key] = (_today_key(), result)
        return dict(result)
