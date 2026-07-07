"""Auto-grade expired sports picks using final scores."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.providers.sports.team_stats import fetch_scores_by_sport
from app.services.performance_service import PerformanceService
from app.services.sports_grading import grade_sports_pick, match_completed_game, scores_from_game

logger = logging.getLogger(__name__)


class OutcomeResolverService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def resolve_pending(self, *, limit: int = 25) -> dict[str, Any]:
        """Grade expired sports signals that have no logged outcome yet."""
        perf_rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "module": "eq.sports",
            },
            limit=500,
        )
        graded_ids = {str(r.get("signal_id")) for r in perf_rows}

        signals = await self.db.select(
            "sports_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": "in.(expired,active)",
            },
            order="event_start.asc",
            limit=limit * 3,
        )

        now = datetime.now(UTC)
        candidates: list[dict[str, Any]] = []
        for sig in signals:
            sid = str(sig.get("id"))
            if sid in graded_ids:
                continue
            event_start = sig.get("event_start")
            if not event_start:
                continue
            try:
                text = str(event_start).replace("Z", "+00:00")
                start = datetime.fromisoformat(text)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                continue
            if start > now:
                continue
            candidates.append(sig)

        if not candidates:
            return {"resolved": 0, "skipped": 0, "pending": 0}

        sport_keys: set[str] = set()
        for sig in candidates[:limit]:
            snap = sig.get("scoring_snapshot") or {}
            key = snap.get("sport_key")
            if key:
                sport_keys.add(str(key))

        scores_by_sport = await fetch_scores_by_sport(sport_keys) if sport_keys else {}

        resolved = 0
        skipped = 0
        for sig in candidates[:limit]:
            snap = sig.get("scoring_snapshot") or {}
            sport_key = str(snap.get("sport_key") or "")
            games = scores_by_sport.get(sport_key) or []
            game = match_completed_game(sig, games)
            if not game:
                skipped += 1
                continue
            parsed = scores_from_game(game)
            if not parsed:
                skipped += 1
                continue
            home_score, away_score, home_team, away_team = parsed
            graded = grade_sports_pick(
                sig,
                home_score=home_score,
                away_score=away_score,
                home_team=home_team,
                away_team=away_team,
            )
            if not graded:
                skipped += 1
                continue
            outcome, return_pct = graded
            try:
                await self.performance.log_outcome(
                    module="sports",
                    signal_id=str(sig["id"]),
                    outcome=outcome,
                    return_pct=return_pct,
                    resolution_source="auto_sports",
                    signal_snapshot=sig,
                )
                await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sig['id']}"},
                    {"status": "closed"},
                )
                resolved += 1
            except Exception as exc:
                logger.warning("Auto-grade sports signal %s: %s", sig.get("id"), exc)
                skipped += 1

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": max(0, len(candidates) - resolved - skipped),
        }
