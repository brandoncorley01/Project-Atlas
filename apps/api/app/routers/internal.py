"""Internal cron endpoints — protected by X-Cron-Secret, not user JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings
from app.jobs.nightly_learning import run_nightly_learning_job
from app.jobs.refresh_sports_intelligence import run_refresh_sports_intelligence_job

router = APIRouter()


def _verify_cron_secret(secret: str | None) -> None:
    expected = (settings.cron_secret or "").strip()
    if not expected or not secret or secret.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Cron-Secret",
        )


@router.post("/internal/jobs/nightly-learning")
async def trigger_nightly_learning(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> dict:
    """Backfill tracking, auto-grade picks, rollup performance, refresh AI intelligence."""
    _verify_cron_secret(x_cron_secret)
    return await run_nightly_learning_job()


@router.post("/internal/jobs/refresh-sports-intelligence")
async def trigger_refresh_sports_intelligence(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> dict:
    """Refresh cached expert/news intelligence for active sports signals."""
    _verify_cron_secret(x_cron_secret)
    return await run_refresh_sports_intelligence_job()


@router.get("/internal/jobs/health")
async def cron_health(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> dict:
    """Ping endpoint for cron secret verification."""
    _verify_cron_secret(x_cron_secret)
    return {
        "status": "ok",
        "default_user_configured": bool(settings.default_user_id),
        "service_role_configured": bool(settings.supabase_service_role_key),
        "openai_configured": bool(settings.openai_api_key),
    }
