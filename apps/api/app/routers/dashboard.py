import asyncio
import logging
from typing import Any, Coroutine, TypeVar

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.alert_service import AlertService
from app.services.dashboard_warnings import (
    append_warning,
    load_status_for,
    warning_summary,
)
from app.services.news_service import NewsService
from app.services.parlay_service import ParlayService
from app.services.performance_service import PerformanceService
from app.services.signal_service import SignalService
from app.services.ai_narrative_service import ai_narrative_service
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.signal_registry_service import SignalRegistryService

logger = logging.getLogger(__name__)

router = APIRouter()

T = TypeVar("T")

_dashboard_sem = asyncio.Semaphore(1)


async def _safe(
    label: str,
    coro: Coroutine[Any, Any, T],
    default: T,
    warnings: list[dict[str, Any]],
) -> T:
    try:
        return await coro
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard %s failed: %s", label, msg)
        append_warning(warnings, label, detail=msg)
        return default


async def _soft(label: str, coro: Coroutine[Any, Any, T], default: T) -> T:
    """Best-effort helper that never emits dashboard warnings."""
    try:
        return await coro
    except Exception as exc:
        logger.info("Dashboard soft %s skipped: %s", label, exc)
        return default


@router.get("/dashboard")
async def get_dashboard(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 10,
) -> dict:
    async with _dashboard_sem:
        return await _build_dashboard(user_id, token, limit)


async def _build_dashboard(user_id: str, token: str, limit: int) -> dict:
    """Fast Home payload — no heavy maintenance on the critical path.

    Expire / backfill / resolve / news refresh live behind POST /engine/fix-all
    so soft timeouts never look like a broken partial load.
    """
    warnings: list[dict[str, Any]] = []
    db = SupabaseClient(token)
    signal_service = SignalService(db, user_id)
    news_service = NewsService(db, user_id)
    parlay_service = ParlayService(db, user_id)
    alert_service = AlertService(db, user_id)
    performance_service = PerformanceService(db, user_id)
    registry = SignalRegistryService(db, user_id)

    (
        top,
        budget,
        stocks,
        sports,
        parlay_rows,
        breaking,
        briefing_news,
        unread_alerts,
        perf_summary,
        tracking_stats,
    ) = await asyncio.gather(
        _safe("top_opportunities", signal_service.top_opportunities(limit=limit), [], warnings),
        _safe("budget_opportunities", signal_service.budget_opportunities(limit=8), [], warnings),
        _safe(
            "stock_opportunities",
            signal_service.stock_opportunities(limit=8, skip_expire=True),
            [],
            warnings,
        ),
        _safe(
            "sports_opportunities",
            signal_service.sports_opportunities(limit=8, skip_expire=True, window="week"),
            [],
            warnings,
        ),
        _safe("list_parlays", parlay_service.list_parlays(limit=1), [], warnings),
        _safe("breaking_news", news_service.breaking_news(limit=5, include_quotes=False), [], warnings),
        _safe("briefing_news", news_service.briefing_news(limit=6), [], warnings),
        _safe("unread_alerts", alert_service.unread_count(), 0, warnings),
        _safe("performance_summary", performance_service.get_summary(days=30), {}, warnings),
        _safe("tracking_stats", registry.tracking_stats(), {}, warnings),
    )

    best_parlay = parlay_rows[0] if parlay_rows else None

    all_opps = top + budget + stocks
    symbols = [
        sym
        for opp in all_opps
        if (sym := SignalService._summary_symbol_from_title(opp.get("title")))
    ]
    catalyst_map = await _soft(
        "catalyst_match",
        news_service.catalysts_for_symbols(symbols),
        {},
    )
    top = signal_service.apply_live_catalysts(top, catalyst_map)
    budget = signal_service.apply_live_catalysts(budget, catalyst_map)
    stocks = signal_service.apply_live_catalysts(stocks, catalyst_map)

    performance_block = {
        "win_rate_30d": perf_summary.get("win_rate") if isinstance(perf_summary, dict) else None,
        "avg_return_30d": perf_summary.get("avg_return_pct") if isinstance(perf_summary, dict) else None,
        "total_logged": perf_summary.get("total_signals") if isinstance(perf_summary, dict) else 0,
        "learning_active": perf_summary.get("learning_active") if isinstance(perf_summary, dict) else False,
        "learning_notes": perf_summary.get("learning_notes") if isinstance(perf_summary, dict) else [],
        "auto_resolved": perf_summary.get("auto_resolved") if isinstance(perf_summary, dict) else 0,
        "tracking": tracking_stats if isinstance(tracking_stats, dict) else {},
    }

    calibration = perf_summary.get("calibration") if isinstance(perf_summary, dict) else {}
    market_intelligence: dict[str, Any] = await _soft(
        "market_intelligence",
        asyncio.wait_for(
            MarketIntelligenceService(db, user_id).generate(
                tracking_stats=tracking_stats if isinstance(tracking_stats, dict) else {},
                perf_summary=perf_summary if isinstance(perf_summary, dict) else {},
                calibration=calibration if isinstance(calibration, dict) else {},
            ),
            timeout=5.0,
        ),
        {},
    )

    needs_refresh = {
        "sports": len(sports) == 0,
        "stocks": len(stocks) == 0,
        "options": len(top) == 0 and len(budget) == 0,
        "news": len(breaking) == 0 and len(briefing_news) == 0,
    }

    briefing_ctx = {
        "top_opportunities": top,
        "budget_opportunities": budget,
        "stock_opportunities": stocks,
        "sports_opportunities": sports,
        "breaking_news": breaking,
        "briefing_news": briefing_news or breaking,
        "best_parlay": best_parlay,
        "performance_summary": performance_block,
        "needs_refresh": needs_refresh,
        "market_intelligence": market_intelligence,
    }

    try:
        atlas_briefing = await asyncio.wait_for(
            ai_narrative_service.daily_briefing(
                user_id=user_id,
                ctx=briefing_ctx,
                refresh=False,
            ),
            timeout=8.0,
        )
    except Exception as exc:
        logger.info("Dashboard atlas_briefing soft fallback: %s", exc)
        atlas_briefing = await ai_narrative_service.daily_briefing(
            user_id=user_id,
            ctx=briefing_ctx,
            use_llm=False,
        )

    load_status = load_status_for(warnings)
    counts = warning_summary(warnings)
    signal_total = len(top) + len(budget) + len(stocks) + len(sports)

    payload = {
        "top_opportunities": top,
        "budget_opportunities": budget,
        "stock_opportunities": stocks,
        "sports_opportunities": sports,
        "best_parlay": best_parlay,
        "breaking_news": breaking,
        "briefing_news": briefing_news or breaking,
        "unread_alerts_count": unread_alerts,
        "atlas_briefing": atlas_briefing,
        "market_intelligence": market_intelligence,
        "performance_summary": performance_block,
        "meta": {
            "user_id": user_id,
            "limit": limit,
            "status": "live" if signal_total else "no_signals",
            "load_status": load_status,
            "news_refreshed": False,
            "warnings": warnings,
            "warning_counts": counts,
            "expired_purged": {},
            "outcomes_resolved": 0,
            "needs_refresh": needs_refresh,
            "fix_all_available": True,
        },
    }

    return jsonable_encoder(payload)
