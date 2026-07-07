from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.jobs.state import set_last_job
from app.services.news_service import NewsService

router = APIRouter()


def _service(user_id: str, token: str) -> NewsService:
    return NewsService(SupabaseClient(token), user_id)


@router.get("/news")
async def list_news(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 20,
    sentiment: str | None = None,
    ticker: str | None = None,
    min_impact: float | None = None,
) -> dict:
    service = _service(user_id, token)
    rows = await service.list_news(
        limit=limit,
        sentiment=sentiment,
        ticker=ticker,
        min_impact=min_impact,
    )
    items = await service.format_items_with_quotes(rows)
    return {"items": items, "total": len(items), "limit": limit}


@router.get("/news/{news_id}")
async def get_news_item(
    news_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    row = await _service(user_id, token).get_news(news_id)
    if not row:
        raise HTTPException(status_code=404, detail="News item not found")
    service = _service(user_id, token)
    items = await service.format_items_with_quotes([row])
    return items[0]


@router.post("/news/refresh")
async def refresh_news(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 40,
) -> dict:
    result = await _service(user_id, token).refresh_news(replace=True, limit=limit)
    set_last_job("refresh_news")
    return {"status": "ok", "module": "news", **result}
