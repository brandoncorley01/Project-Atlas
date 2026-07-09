from fastapi import APIRouter, Depends, HTTPException

from app.agents.parlay_builder import build_custom_parlay
from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.parlay_service import ParlayService
from app.services.signal_service import SignalService

router = APIRouter()


def _service(user_id: str, token: str) -> ParlayService:
    return ParlayService(SupabaseClient(token), user_id)


@router.get("/parlays/categories")
async def list_parlay_categories(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    categories = await _service(user_id, token).parlay_category_catalog()
    return {"categories": categories}


@router.get("/parlays/categories/{slug}")
async def get_parlay_category(
    slug: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 50,
) -> dict:
    detail = await _service(user_id, token).parlay_category_detail(slug, limit=limit)
    if not detail:
        raise HTTPException(status_code=404, detail="Category not found")
    return detail


@router.get("/parlays")
async def list_parlays(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    style: str | None = None,
    category: str | None = None,
    limit: int = 50,
    status: str = "active",
) -> dict:
    service = _service(user_id, token)
    items = await service.list_parlays(
        style=style,
        category=category,
        limit=limit,
        status=status,
    )
    return {
        "items": items,
        "total": len(items),
        "limit": limit,
        "style": style,
        "category": category,
    }


@router.post("/parlays")
async def create_parlay(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    signal_ids = body.get("signal_ids") or body.get("sports_signal_ids") or []
    if not isinstance(signal_ids, list) or len(signal_ids) < 2:
        raise HTTPException(status_code=400, detail="signal_ids must be a list of at least 2 IDs")

    service = _service(user_id, token)
    try:
        parlay = await service.create_custom_parlay([str(sid) for sid in signal_ids[:6]])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"parlay": parlay}


@router.post("/parlays/calculate")
async def calculate_parlay(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    signal_ids = body.get("signal_ids") or body.get("sports_signal_ids") or []
    if not isinstance(signal_ids, list) or len(signal_ids) < 2:
        raise HTTPException(status_code=400, detail="signal_ids must be a list of at least 2 IDs")

    sports = SignalService(SupabaseClient(token), user_id)
    signals: list[dict] = []
    for sid in signal_ids[:6]:
        row = await sports.get_sports(str(sid))
        if not row:
            raise HTTPException(status_code=404, detail=f"Sports signal not found: {sid}")
        signals.append(row)

    try:
        parlay = build_custom_parlay(signals)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"parlay": parlay}


@router.get("/parlays/{parlay_id}")
async def get_parlay(
    parlay_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    for_edit: bool = False,
) -> dict:
    service = _service(user_id, token)
    row = await service.get_parlay(parlay_id, for_edit=for_edit)
    if not row:
        raise HTTPException(status_code=404, detail="Parlay not found")
    return await service.format_parlay_with_legs(row)


@router.patch("/parlays/{parlay_id}")
async def update_parlay(
    parlay_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    signal_ids = body.get("signal_ids") or body.get("sports_signal_ids") or []
    if not isinstance(signal_ids, list) or len(signal_ids) < 2:
        raise HTTPException(status_code=400, detail="signal_ids must be a list of at least 2 IDs")

    service = _service(user_id, token)
    try:
        parlay = await service.update_parlay_legs(parlay_id, [str(sid) for sid in signal_ids[:6]])
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"parlay": parlay}
