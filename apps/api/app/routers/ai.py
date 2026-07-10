from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import logging
from datetime import UTC, datetime

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.ai_narrative_service import ai_narrative_service
from app.services.llm_service import llm_service
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.performance_service import PerformanceService
from app.services.signal_registry_service import SignalRegistryService
from app.services.signal_service import SignalService
from app.services.sports_insight_service import sports_insight_service

router = APIRouter()
logger = logging.getLogger(__name__)


class ExplainRequest(BaseModel):
    module: str = Field(..., pattern="^(options|stock|sports)$")
    signal_id: str = Field(..., min_length=8)


@router.get("/ai/status")
async def ai_status() -> dict:
    configured = llm_service.is_configured()
    connected = False
    error: str | None = None
    if configured:
        connected, error = await llm_service.probe_connection()
    return {
        "configured": configured,
        "connected": connected and configured,
        "model": llm_service.model if configured else None,
        "error": error,
        "features": [
            "auto-track every scan pick",
            "daily briefing",
            "market intelligence",
            "coach insight",
            "deeper pick explanations",
        ],
    }


@router.get("/ai/briefing")
async def get_briefing(
    refresh: bool = False,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    from app.routers.dashboard import _build_dashboard

    dashboard = await _build_dashboard(user_id, token, limit=8)
    ctx = {
        "top_opportunities": dashboard.get("top_opportunities") or [],
        "budget_opportunities": dashboard.get("budget_opportunities") or [],
        "stock_opportunities": dashboard.get("stock_opportunities") or [],
        "sports_opportunities": dashboard.get("sports_opportunities") or [],
        "breaking_news": dashboard.get("breaking_news") or [],
        "best_parlay": dashboard.get("best_parlay"),
        "performance_summary": dashboard.get("performance_summary") or {},
        "needs_refresh": (dashboard.get("meta") or {}).get("needs_refresh") or {},
        "market_intelligence": dashboard.get("market_intelligence") or {},
    }
    briefing = await ai_narrative_service.daily_briefing(
        user_id=user_id,
        ctx=ctx,
        refresh=refresh,
    )
    return briefing


@router.get("/ai/coach-insight")
async def get_coach_insight(
    refresh: bool = False,
    days: int = 30,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    summary: dict = {
        "days": days,
        "total_signals": 0,
        "pending": 0,
        "by_module": {},
        "learning_notes": [],
    }
    try:
        perf = PerformanceService(SupabaseClient(token), user_id)
        summary = await perf.get_summary(days=days)
    except Exception as exc:
        logger.warning("coach_insight summary failed for %s: %s", user_id, exc)

    try:
        return await ai_narrative_service.coach_insight(
            user_id=user_id,
            summary=summary,
            refresh=refresh,
        )
    except Exception:
        logger.exception("coach_insight narrative failed for %s", user_id)
        return {
            "narrative": ai_narrative_service._template_coach(summary),
            "focus_areas": ai_narrative_service._coach_focus_areas(summary),
            "by_module": ai_narrative_service._coach_by_module(summary),
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "template",
            "model": None,
        }


@router.post("/ai/explain")
async def explain_signal(
    body: ExplainRequest,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = SignalService(SupabaseClient(token), user_id)
    module = body.module

    if module == "options":
        row = await service.get_options(body.signal_id)
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")
        formatted = service.format_options_item(row)
    elif module == "stock":
        row = await service.get_stock(body.signal_id)
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")
        formatted = service.format_stock_item(row)
    else:
        row = await service.get_sports(body.signal_id)
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")
        formatted = service.format_sports_item(row)
        try:
            result = await sports_insight_service.explain_pick(signal=row, formatted=formatted)
        except Exception:
            logger.exception("Sports insight failed for %s", body.signal_id)
            context = await sports_insight_service.gather_context(row, formatted)
            thesis = context.get("pick_thesis") or str(
                formatted.get("explanation") or row.get("explanation")
                or "Insight is limited right now — scan data is still available above."
            )
            result = {
                "explanation": thesis,
                "why_atlas": thesis,
                "pick_thesis": thesis,
                "bullets": sports_insight_service._template_bullets(formatted, row, context),
                "risks": sports_insight_service._template_risks(formatted, row, context),
                "news_articles": context["news_articles"],
                "stats_comparison": context["stats_comparison"],
                "market": context.get("market"),
                "source": "template",
                "model": None,
            }
        return {
            "module": module,
            "signal_id": body.signal_id,
            "title": formatted.get("title"),
            **result,
        }

    result = await ai_narrative_service.explain_signal(
        module=module,
        signal=row,
        formatted=formatted,
    )
    return {
        "module": module,
        "signal_id": body.signal_id,
        "title": formatted.get("title"),
        **result,
    }


@router.get("/ai/intelligence")
async def get_market_intelligence(
    refresh: bool = False,
    days: int = 30,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    db = SupabaseClient(token)
    perf = PerformanceService(db, user_id)
    registry = SignalRegistryService(db, user_id)
    summary = await perf.get_summary(days=days)
    tracking = await registry.tracking_stats()
    calibration = summary.get("calibration") or {}
    intelligence = await MarketIntelligenceService(db, user_id).generate(
        tracking_stats=tracking,
        perf_summary=summary,
        calibration=calibration,
        refresh=refresh,
    )
    return {"tracking": tracking, "intelligence": intelligence}


@router.post("/ai/backfill-tracking")
async def backfill_tracking(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    """Register historical signals that were never tracked."""
    registry = SignalRegistryService(SupabaseClient(token), user_id)
    result = await registry.backfill_all(limit_per_module=200)
    tracking = await registry.tracking_stats()
    return {"status": "ok", **result, "tracking": tracking}
