"""Nightly learning flywheel — backfill, auto-grade, coach rollup, AI intelligence.

Run on Render cron every 6 hours:
    python -m app.jobs.nightly_learning
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.config import settings
from app.db.service_client import get_service_db
from app.jobs.coach_aggregate import run_coach_aggregate_job
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.outcome_resolver import OutcomeResolverService
from app.services.performance_service import PerformanceService
from app.services.signal_registry_service import SignalRegistryService

logger = logging.getLogger(__name__)


async def run_nightly_learning_job(*, user_id: str | None = None) -> dict:
    """Auto-track, grade, aggregate, and refresh AI market intelligence."""
    uid = (user_id or settings.default_user_id or "").strip()
    if not uid:
        logger.warning("DEFAULT_USER_ID not set — skipping nightly learning")
        return {"status": "skipped", "reason": "DEFAULT_USER_ID not set"}

    if not settings.supabase_service_role_key:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY not set — skipping nightly learning")
        return {"status": "skipped", "reason": "SUPABASE_SERVICE_ROLE_KEY not set"}

    token = settings.supabase_service_role_key.strip()
    db = get_service_db()

    registry = SignalRegistryService(db, uid)
    backfill = await registry.backfill_all(limit_per_module=200)

    resolve = await OutcomeResolverService(db, uid).resolve_pending(limit=60)

    coach = await run_coach_aggregate_job(uid, token, days=30)

    tracking = await registry.tracking_stats()
    perf = await PerformanceService(db, uid).get_summary(days=30)
    calibration = perf.get("calibration") or {}

    intelligence = await MarketIntelligenceService(db, uid).generate(
        tracking_stats=tracking,
        perf_summary=perf,
        calibration=calibration,
        refresh=True,
    )

    result = {
        "status": "ok",
        "module": "nightly_learning",
        "user_id": uid,
        "backfill": backfill,
        "resolve": resolve,
        "coach_status": coach.get("status"),
        "tracking": tracking,
        "intelligence": {
            "source": intelligence.get("source"),
            "headline": intelligence.get("headline"),
            "sample_count": intelligence.get("sample_count"),
        },
    }
    logger.info("Nightly learning complete: %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = asyncio.run(run_nightly_learning_job())
    print(result)
    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
