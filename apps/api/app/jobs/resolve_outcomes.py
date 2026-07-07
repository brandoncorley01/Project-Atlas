"""Auto-grade expired picks when final scores are available."""

from __future__ import annotations

from app.db.supabase_client import SupabaseClient
from app.services.outcome_resolver import OutcomeResolverService


async def run_resolve_outcomes_job(user_id: str, token: str, *, limit: int = 25) -> dict:
    service = OutcomeResolverService(SupabaseClient(token), user_id)
    result = await service.resolve_pending(limit=limit)
    return {"status": "ok", "module": "resolve_outcomes", **result}
