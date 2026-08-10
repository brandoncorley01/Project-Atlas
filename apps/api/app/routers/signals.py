from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.signal_service import SignalService

router = APIRouter()


def _service(user_id: str, token: str) -> SignalService:
    return SignalService(SupabaseClient(token), user_id)


@router.get("/options")
async def list_options_signals(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 20,
    offset: int = 0,
    sort: str = "opportunity_score",
    status: str = "active",
    budget: bool = False,
) -> dict:
    service = _service(user_id, token)
    items = await service.list_options(
        limit=limit, offset=offset, status=status, budget_only=budget
    )
    formatted = [service.format_options_item(row) for row in items]
    return {
        "items": formatted,
        "total": len(formatted),
        "limit": limit,
        "offset": offset,
        "budget": budget,
    }


@router.get("/options/{signal_id}")
async def get_options_signal(
    signal_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = _service(user_id, token)
    row = await service.get_options(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")
    return service.format_options_item(row)


@router.get("/stocks")
async def list_stock_signals(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 20,
    offset: int = 0,
    status: str = "active",
) -> dict:
    service = _service(user_id, token)
    rows = await service.list_stocks(limit=limit, offset=offset, status=status)
    items = [service.format_stock_item(row) for row in rows]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.get("/stocks/{signal_id}")
async def get_stock_signal(
    signal_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    row = await _service(user_id, token).get_stock(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock signal not found")
    return _service(user_id, token).format_stock_item(row)


@router.get("/sports/categories")
async def list_sports_categories(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    categories = await _service(user_id, token).sports_category_catalog()
    return {"categories": categories}


@router.get("/sports/categories/{slug}")
async def get_sports_category(
    slug: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 30,
) -> dict:
    detail = await _service(user_id, token).sports_category_detail(slug, limit=limit)
    if not detail:
        raise HTTPException(status_code=404, detail="Category not found")
    return detail


@router.get("/sports/events")
async def search_sports_events(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    q: str = "",
    sport: str | None = None,
    limit: int = 40,
    all_sports: bool = True,
) -> dict:
    """Atlas Insight search — FanDuel/DK verified markets across the full board."""
    from app.services.signal_service import SignalService
    from app.services.sports_openai_search_service import search_markets_with_openai

    board_rows: list[dict] = []
    try:
        board_rows = await SignalService(SupabaseClient(token), user_id).list_all_sports(
            limit=200,
        )
    except Exception:
        board_rows = []

    return await search_markets_with_openai(
        query=q,
        sport=sport,
        limit=limit,
        all_sports=all_sports,
        board_signals=board_rows,
    )


@router.post("/sports/user-bets")
async def create_sports_user_bet(
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    """Log a user bet/pick for Atlas tracking and learning (0 Odds API credits)."""
    from app.services.sports_user_bets_service import SportsUserBetsService

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body required")
    result = await SportsUserBetsService(SupabaseClient(token), user_id).create_user_bet(payload)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Could not save bet")
    item = result.get("item")
    formatted = _service(user_id, token).format_sports_item(item) if item else None
    return {**result, "item": formatted}


@router.post("/sports/user-bets/recover")
async def recover_sports_user_bets(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    """Reactivate Search bets that were incorrectly expired or purged from the board."""
    from app.services.sports_user_bets_service import SportsUserBetsService

    return await SportsUserBetsService(SupabaseClient(token), user_id).recover_user_bets()


@router.get("/sports")
async def list_sports_signals(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    sport: str | None = None,
    category: str | None = None,
    window: str = "soon",
    limit: int = 20,
    offset: int = 0,
    status: str = "active",
) -> dict:
    """List saved sports picks.

    Read path skips expire/resolve so navigating back to Sports stays fast and
    does not wipe the board. Concluded games are still filtered via is_sports_listable.
    Expire + grade run on Scan / Rescore / cron / Performance.
    """
    service = _service(user_id, token)
    rows = await service.list_sports(
        limit=limit,
        offset=offset,
        status=status,
        sport=sport,
        category=category,
        window=window,
        skip_expire=True,
    )
    items = [service.format_sports_item(row) for row in rows]
    try:
        from app.services.kalshi_public_pulse import enrich_sports_rows_with_kalshi

        # Prices only on list — history candles made the enrich timeout so cards stayed empty.
        items = await enrich_sports_rows_with_kalshi(
            items,
            max_rows=min(len(items), 48),
            include_history=False,
            timeout_sec=8.0,
        )
    except Exception:
        pass

    board_as_of = None
    for item in items:
        raw = item.get("data_as_of")
        if isinstance(raw, str) and raw:
            if board_as_of is None or raw > board_as_of:
                board_as_of = raw

    odds_meta: dict = {}
    try:
        from app.providers.sports.odds_api import odds_cache_status
        from app.jobs.state import LAST_JOBS

        cache = odds_cache_status()
        odds_meta = {
            "odds_fetched_at": cache.get("fetched_at"),
            "odds_age_minutes": cache.get("age_minutes"),
            "last_sports_job_at": LAST_JOBS.get("refresh_sports"),
            "last_insight_job_at": LAST_JOBS.get("refresh_sports_openai"),
        }
    except Exception:
        pass

    return {
        "items": items,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "sport": sport,
        "category": category,
        "window": window,
        "meta": {
            "board_as_of": board_as_of,
            "persisted": True,
            **odds_meta,
        },
    }


@router.get("/sports/{signal_id}")
async def get_sports_signal(
    signal_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = _service(user_id, token)
    row = await service.get_sports(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Sports signal not found")
    item = service.format_sports_item(row)
    try:
        from app.services.kalshi_public_pulse import enrich_sports_rows_with_kalshi

        enriched = await enrich_sports_rows_with_kalshi([item], max_rows=1, timeout_sec=4.0)
        item = enriched[0] if enriched else item
    except Exception:
        pass
    return item


@router.get("/top")
async def list_top_signals(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 10,
    modules: str | None = None,
) -> dict:
    items = await _service(user_id, token).top_opportunities(limit=limit)
    return {"items": items, "total": len(items), "limit": limit, "modules": modules}
