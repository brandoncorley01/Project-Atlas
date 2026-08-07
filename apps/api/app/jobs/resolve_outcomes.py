"""Auto-grade expired picks when final scores are available."""

from __future__ import annotations

from app.db.supabase_client import SupabaseClient
from app.services.outcome_resolver import OutcomeResolverService


async def run_resolve_outcomes_job(
    user_id: str,
    token: str,
    *,
    limit: int = 150,
    module: str | None = None,
    passes: int = 4,
) -> dict:
    """Walk the open backlog in multiple passes.

    Large Atlas open piles (hundreds of pending props) previously consumed a
    single small batch and left finished moneylines forever at 0 graded.
    """
    service = OutcomeResolverService(SupabaseClient(token), user_id)
    result = await service.resolve_pending(limit=limit, module=module, passes=passes)
    return {"status": "ok", "module": "resolve_outcomes", **result}
