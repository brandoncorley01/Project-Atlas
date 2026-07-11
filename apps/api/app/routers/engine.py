from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.engine.pipeline import mock_options_candidates
from app.agents.analyst import rank_scored, score_candidate
from app.agents.scout import filter_candidates
from app.jobs.state import set_last_job
from app.jobs.refresh_news import run_refresh_news_job
from app.jobs.refresh_stocks import run_refresh_stocks_job
from app.jobs.refresh_sports import run_refresh_sports_job
from app.jobs.build_parlays import run_build_parlays_job
from app.jobs.coach_aggregate import run_coach_aggregate_job
from app.jobs.resolve_outcomes import run_resolve_outcomes_job
from app.services.options_service import OptionsRefreshService
from app.services.signal_service import SignalService

router = APIRouter()


def _service(user_id: str, token: str) -> SignalService:
    return SignalService(SupabaseClient(token), user_id)


@router.post("/refresh-stocks")
async def refresh_stocks(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    replace: bool = True,
    limit: int = 15,
) -> dict:
    """Scan market for ranked stock swing setups with RSI, MACD, and RVOL."""
    from app.services.stock_service import StockRefreshService

    service = StockRefreshService(SupabaseClient(token), user_id)
    result = await service.refresh_stocks(replace=replace, limit=limit)
    set_last_job("refresh_stocks")
    return {"status": "ok", "module": "stocks", **result}


@router.post("/analyze-stock")
async def analyze_stock(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    ticker: str = "",
    persist: bool = False,
) -> dict:
    """Full swing analysis for a single ticker — chart, entry, stop, and targets."""
    from app.services.stock_service import StockRefreshService

    service = StockRefreshService(SupabaseClient(token), user_id)
    result = await service.analyze_ticker(ticker, persist=persist)
    if not result.get("ok"):
        return {"status": "error", "module": "stocks", **result}
    set_last_job("analyze_stock")
    return {"status": "ok", "module": "stocks", **result}


@router.post("/refresh-sports")
async def refresh_sports(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    replace: bool = True,
    limit: int = 120,
    force_refresh: bool = False,
    cache_only: bool = False,
) -> dict:
    """Fetch odds from The Odds API and rank +EV moneyline, spread, total, and futures plays.

    - Default / Scan: use warm cache when available, otherwise live pull.
    - force_refresh=true (Fetch live odds): spend Odds credits for US-core books.
    - cache_only=true (Rescore): never spend Odds credits; requires existing cache.
    """
    from app.services.sports_service import SportsRefreshService

    if force_refresh and cache_only:
        raise HTTPException(status_code=400, detail="force_refresh and cache_only cannot both be true")

    service = SportsRefreshService(SupabaseClient(token), user_id)
    result = await service.refresh_sports(
        replace=replace,
        limit=limit,
        force_refresh=force_refresh,
        cache_only=cache_only,
    )
    set_last_job("refresh_sports")
    return {"status": "ok", "module": "sports", **result}


@router.post("/refresh-sports-openai")
async def refresh_sports_openai(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 16,
) -> dict:
    """Atlas Insight — find analyst / popular-bettor picks from the public internet.

    Uses OPENAI_API_KEY + web search. Does not spend Odds API credits.
    Merges onto the board without wiping Odds-derived picks.
    """
    from app.services.sports_openai_picks_service import SportsOpenAiPicksService

    service = SportsOpenAiPicksService(SupabaseClient(token), user_id)
    result = await service.refresh_openai_picks(limit=limit)
    set_last_job("refresh_sports_openai")
    return {"status": "ok", "module": "sports_openai", **result}


@router.post("/coach-aggregate")
async def coach_aggregate(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    days: int = 30,
) -> dict:
    """Roll up logged outcomes into performance summaries."""
    result = await run_coach_aggregate_job(user_id, token, days=days)
    set_last_job("coach_aggregate")
    return result


@router.post("/resolve-outcomes")
async def resolve_outcomes(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 25,
    module: str | None = None,
) -> dict:
    """Auto-grade finished sports, stock, options, and parlay picks for Atlas learning."""
    if module is not None and module not in ("sports", "stock", "options", "parlay"):
        raise HTTPException(
            status_code=400,
            detail="module must be one of: sports, stock, options, parlay",
        )
    result = await run_resolve_outcomes_job(user_id, token, limit=limit, module=module)
    set_last_job("resolve_outcomes")
    return result


@router.post("/build-parlays")
async def build_parlays(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    replace: bool = True,
) -> dict:
    """Combine top sports signals into conservative, balanced, and aggressive parlays."""
    from app.services.parlay_service import ParlayService

    service = ParlayService(SupabaseClient(token), user_id)
    result = await service.build_parlays(replace=replace)
    set_last_job("build_parlays")
    return {"status": "ok", "module": "parlays", **result}


@router.post("/refresh-news")
async def refresh_news(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    """Ingest Finnhub + RSS, classify, and persist news catalysts."""
    result = await run_refresh_news_job(user_id, token)
    return {"status": "ok", "module": "news", **result}


@router.post("/refresh-options")
async def refresh_live_options(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    replace: bool = True,
    limit: int = 15,
) -> dict:
    """Discover market movers, deep-scan options chains, rank by profit probability."""
    service = OptionsRefreshService(SupabaseClient(token), user_id)
    result = await service.refresh_live_options(replace=replace, limit=limit)
    set_last_job("refresh_options")
    return {"status": "ok", "module": "options", **result}


@router.post("/run-mock")
async def run_mock_pipeline(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    replace: bool = True,
) -> dict:
    """Run Opportunity Engine on mock data and persist options signals."""
    total = len(mock_options_candidates())
    service = _service(user_id, token)
    saved = await service.run_mock_options_pipeline(replace=replace)
    set_last_job("refresh_options")
    return {
        "status": "ok",
        "module": "options",
        "signals_created": len(saved),
        "filtered_out": total - len(saved),
    }


@router.get("/preview-mock")
async def preview_mock_pipeline(
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Preview scoring without saving."""
    candidates = mock_options_candidates()
    filtered = filter_candidates(candidates)
    scored = rank_scored([score_candidate(c) for c in filtered])

    return {
        "total_candidates": len(candidates),
        "passed_scout": len(filtered),
        "preview": [
            {
                "symbol": s.candidate.symbol,
                "confidence": s.confidence_score,
                "risk": s.risk_score,
                "opportunity": s.opportunity_score,
            }
            for s in scored
        ],
    }
