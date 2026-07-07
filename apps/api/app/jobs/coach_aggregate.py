"""Nightly performance rollup — aggregates logged outcomes into summaries."""

from __future__ import annotations

from app.db.supabase_client import SupabaseClient
from app.services.performance_service import PerformanceService


async def run_coach_aggregate_job(user_id: str, token: str, *, days: int = 30) -> dict:
    service = PerformanceService(SupabaseClient(token), user_id)
    summary = await service.aggregate_and_store(days=days)
    return {"status": "ok", "module": "coach", "summary": summary}
