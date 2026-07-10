"""Refresh sports intelligence for active signals (cron or post-scan)."""

from __future__ import annotations

import logging

from app.config import settings
from app.db.service_client import get_service_db
from app.sports_intelligence.service import SportsIntelligenceService

logger = logging.getLogger(__name__)


async def run_refresh_sports_intelligence_job(*, limit: int = 12) -> dict:
    if not settings.is_intelligence_enabled():
        return {"enabled": False, "refreshed": 0}

    user_id = (settings.default_user_id or "").strip()
    if not user_id:
        return {"enabled": True, "refreshed": 0, "error": "DEFAULT_USER_ID not configured"}

    db = get_service_db()
    rows = await db.select(
        "sports_signals",
        filters={"user_id": f"eq.{user_id}", "status": "eq.active"},
        order="opportunity_score.desc",
        limit=limit,
    )
    service = SportsIntelligenceService(db, user_id)
    return await service.refresh_active_signals(rows, limit=limit)
