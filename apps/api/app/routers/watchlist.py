import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)

router = APIRouter()


def _friendly_watchlist_error(exc: HTTPException) -> HTTPException:
    detail = str(exc.detail) if exc.detail else "Could not save to watchlist"
    lowered = detail.lower()
    if "foreign key" in lowered and "profiles" in lowered:
        return HTTPException(
            status_code=400,
            detail="Account profile missing — sign out, sign in again, then retry.",
        )
    if "foreign key" in lowered:
        return HTTPException(status_code=400, detail="Could not save — account setup incomplete.")
    if "check constraint" in lowered or "item_type_check" in lowered:
        return HTTPException(
            status_code=400,
            detail="Watchlist type not supported on this database — run the latest Supabase migration.",
        )
    if exc.status_code >= 500:
        logger.error("Watchlist database error: %s", detail[:500])
        return HTTPException(status_code=400, detail=f"Could not save to watchlist: {detail[:240]}")
    return exc


@router.get("/watchlist")
async def get_watchlist(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = WatchlistService(SupabaseClient(token), user_id)
    return await service.get_watchlist()


@router.post("/watchlist/items")
async def add_watchlist_item(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    item_type = str(body.get("item_type") or "ticker")
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    service = WatchlistService(SupabaseClient(token), user_id)
    try:
        item = await service.add_item(symbol=symbol, item_type=item_type, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException as exc:
        raise _friendly_watchlist_error(exc) from exc
    return {"status": "created", "item": item}


@router.delete("/watchlist/items/{item_id}")
async def remove_watchlist_item(
    item_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = WatchlistService(SupabaseClient(token), user_id)
    removed = await service.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"status": "deleted", "id": item_id}
