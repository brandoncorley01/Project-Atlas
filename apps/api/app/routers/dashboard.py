import asyncio
import logging
from typing import Any, Coroutine, TypeVar

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.alert_service import AlertService
from app.services.news_service import NewsService
from app.services.parlay_service import ParlayService
from app.services.performance_service import PerformanceService
from app.services.signal_service import SignalService
from app.services.stale_signal_service import StaleSignalService
from app.jobs.resolve_outcomes import run_resolve_outcomes_job
from app.services.ai_narrative_service import ai_narrative_service
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.signal_registry_service import SignalRegistryService

logger = logging.getLogger(__name__)

router = APIRouter()

T = TypeVar("T")

_dashboard_sem = asyncio.Semaphore(1)
_EXPIRE_BUDGET_SEC = 10.0


async def _safe(label: str, coro: Coroutine[Any, Any, T], default: T, warnings: list[str]) -> T:
    try:
        return await coro
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard %s failed: %s", label, msg)
        warnings.append(f"{label}: {msg}")
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
    warnings: list[str] = []
    db = SupabaseClient(token)
    signal_service = SignalService(db, user_id)
    news_service = NewsService(db, user_id)
    parlay_service = ParlayService(db, user_id)
    alert_service = AlertService(db, user_id)
    performance_service = PerformanceService(db, user_id)

    try:
        expired_counts = await asyncio.wait_for(
            StaleSignalService(db, user_id).expire_all(),
            timeout=_EXPIRE_BUDGET_SEC,
        )
    except TimeoutError:
        logger.warning("Dashboard expire_stale timed out after %.0fs", _EXPIRE_BUDGET_SEC)
        warnings.append("expire_stale: timed out (skipped)")
        expired_counts = {}
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard expire_stale failed: %s", msg)
        warnings.append(f"expire_stale: {msg}")
        expired_counts = {}

    resolve_stats: dict[str, Any] = {}
    registry = SignalRegistryService(db, user_id)

    try:
        await asyncio.wait_for(registry.backfill_all(limit_per_module=80), timeout=6.0)
    except TimeoutError:
        warnings.append("signal_backfill: timed out (skipped)")
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard signal_backfill failed: %s", msg)
        warnings.append(f"signal_backfill: {msg}")

    try:
        resolve_stats = await asyncio.wait_for(
            run_resolve_outcomes_job(user_id, token, limit=35),
            timeout=18.0,
        )
    except TimeoutError:
        warnings.append("resolve_outcomes: timed out (skipped)")
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard resolve_outcomes failed: %s", msg)
        warnings.append(f"resolve_outcomes: {msg}")

    (
        top,
        budget,
        stocks,
        sports,
        parlay_rows,
        breaking,
        unread_alerts,
        perf_summary,
        tracking_stats,
    ) = await asyncio.gather(
        _safe("top_opportunities", signal_service.top_opportunities(limit=limit), [], warnings),
        _safe("budget_opportunities", signal_service.budget_opportunities(limit=8), [], warnings),
        _safe("stock_opportunities", signal_service.stock_opportunities(limit=8, skip_expire=True), [], warnings),
        _safe("sports_opportunities", signal_service.sports_opportunities(limit=8, skip_expire=True), [], warnings),
        _safe("list_parlays", parlay_service.list_parlays(limit=1), [], warnings),
        _safe("breaking_news", news_service.breaking_news(limit=5, include_quotes=False), [], warnings),
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
    catalyst_map = await _safe(
        "catalyst_match",
        news_service.catalysts_for_symbols(symbols),
        {},
        warnings,
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
    market_intelligence: dict[str, Any] = {}
    try:
        market_intelligence = await asyncio.wait_for(
            MarketIntelligenceService(db, user_id).generate(
                tracking_stats=tracking_stats if isinstance(tracking_stats, dict) else {},
                perf_summary=perf_summary if isinstance(perf_summary, dict) else {},
                calibration=calibration if isinstance(calibration, dict) else {},
            ),
            timeout=8.0,
        )
    except TimeoutError:
        warnings.append("market_intelligence: timed out (skipped)")
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard market_intelligence failed: %s", msg)
        warnings.append(f"market_intelligence: {msg}")

    needs_refresh = {
        "sports": len(sports) == 0,
        "stocks": len(stocks) == 0,
        "options": len(top) == 0 and len(budget) == 0,
        "news": len(breaking) == 0,
    }

    briefing_ctx = {
        "top_opportunities": top,
        "budget_opportunities": budget,
        "stock_opportunities": stocks,
        "sports_opportunities": sports,
        "breaking_news": breaking,
        "best_parlay": best_parlay,
        "performance_summary": performance_block,
        "needs_refresh": needs_refresh,
        "market_intelligence": market_intelligence,
    }

    atlas_briefing: dict[str, Any] = {}
    try:
        atlas_briefing = await asyncio.wait_for(
            ai_narrative_service.daily_briefing(user_id=user_id, ctx=briefing_ctx),
            timeout=8.0,
        )
    except TimeoutError:
        warnings.append("atlas_briefing: timed out (template only)")
        atlas_briefing = await ai_narrative_service.daily_briefing(
            user_id=user_id,
            ctx=briefing_ctx,
            use_llm=False,
        )
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("Dashboard atlas_briefing failed: %s", msg)
        warnings.append(f"atlas_briefing: {msg}")
        atlas_briefing = await ai_narrative_service.daily_briefing(
            user_id=user_id,
            ctx=briefing_ctx,
            use_llm=False,
        )

    payload = {
        "top_opportunities": top,
        "budget_opportunities": budget,
        "stock_opportunities": stocks,
        "sports_opportunities": sports,
        "best_parlay": best_parlay,
        "breaking_news": breaking,
        "unread_alerts_count": unread_alerts,
        "atlas_briefing": atlas_briefing,
        "market_intelligence": market_intelligence,
        "performance_summary": performance_block,
        "meta": {
            "user_id": user_id,
            "limit": limit,
            "status": "live" if top else "no_signals",
            "warnings": warnings,
            "expired_purged": expired_counts,
            "outcomes_resolved": resolve_stats.get("resolved", 0),
            "outcomes_by_module": resolve_stats.get("by_module"),
            "needs_refresh": needs_refresh,
        },
    }

    return jsonable_encoder(payload)
