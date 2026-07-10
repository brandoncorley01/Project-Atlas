from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.calibration_service import CalibrationService
from app.services.performance_service import PerformanceService

router = APIRouter()


@router.post("/performance/sync-watchlist")
async def sync_watchlist_performance(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    """Register every saved watchlist pick into signal_performance."""
    from app.services.watchlist_service import WatchlistService

    wl = await WatchlistService(SupabaseClient(token), user_id).get_watchlist()
    perf = PerformanceService(SupabaseClient(token), user_id)
    synced = 0
    already_tracked = 0
    skipped = 0
    errors: list[str] = []
    items = wl.get("items") or []
    for item in items:
        resolved = PerformanceService.resolve_watchlist_item(item)
        if not resolved:
            skipped += 1
            continue
        module, signal_id, _snapshot = resolved
        try:
            existing = await perf.get_outcome(module=module, signal_id=signal_id)
            result = await perf.register_from_watchlist(item=item)
            if not result:
                skipped += 1
                continue
            if existing:
                already_tracked += 1
            else:
                synced += 1
        except Exception as exc:
            skipped += 1
            errors.append(str(exc)[:120])
    return {
        "status": "ok",
        "synced": synced,
        "registered": synced,
        "already_tracked": already_tracked,
        "skipped": skipped,
        "total": len(items),
        "trackable": synced + already_tracked,
        "errors": errors[:5],
    }


@router.get("/performance/summary")
async def get_performance_summary(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    days: int = 30,
    module: str | None = None,
) -> dict:
    service = PerformanceService(SupabaseClient(token), user_id)
    return await service.get_summary(days=days, module=module)


@router.get("/performance/calibration")
async def get_performance_calibration(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = CalibrationService(SupabaseClient(token), user_id)
    return await service.get_adjustments()


@router.get("/performance/outcome")
async def get_signal_outcome(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    module: str = Query(...),
    signal_id: str = Query(...),
) -> dict:
    service = PerformanceService(SupabaseClient(token), user_id)
    entry = await service.get_outcome(module=module, signal_id=signal_id)
    return {"outcome": entry}


@router.get("/performance/history")
async def get_performance_history(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    limit: int = 50,
    offset: int = 0,
    module: str | None = None,
    resolved_only: bool = False,
    pending_only: bool = False,
) -> dict:
    service = PerformanceService(SupabaseClient(token), user_id)
    return await service.get_history(
        limit=limit,
        offset=offset,
        module=module,
        resolved_only=resolved_only,
        pending_only=pending_only,
    )


@router.post("/performance")
async def log_performance(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    module = str(body.get("module") or "").strip()
    signal_id = str(body.get("signal_id") or "").strip()
    outcome = str(body.get("outcome") or "").strip()
    if not module or not signal_id or not outcome:
        raise HTTPException(status_code=400, detail="module, signal_id, and outcome are required")

    return_pct = body.get("return_pct")
    hold_hours = body.get("hold_duration_hours")
    resolution_source = str(body.get("resolution_source") or "manual")
    signal_snapshot = body.get("signal_snapshot") if isinstance(body.get("signal_snapshot"), dict) else None
    service = PerformanceService(SupabaseClient(token), user_id)
    try:
        entry = await service.log_outcome(
            module=module,
            signal_id=signal_id,
            outcome=outcome,
            return_pct=float(return_pct) if return_pct is not None else None,
            hold_duration_hours=float(hold_hours) if hold_hours is not None else None,
            resolution_source=resolution_source,
            signal_snapshot=signal_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "logged", "entry": entry}


@router.patch("/performance/{outcome_id}")
async def update_performance(
    outcome_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    outcome = body.get("outcome")
    if outcome is not None:
        outcome = str(outcome).strip()
    return_pct = body.get("return_pct")
    hold_hours = body.get("hold_duration_hours")

    service = PerformanceService(SupabaseClient(token), user_id)
    try:
        entry = await service.update_outcome(
            outcome_id,
            outcome=outcome,
            return_pct=float(return_pct) if return_pct is not None else None,
            hold_duration_hours=float(hold_hours) if hold_hours is not None else None,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"status": "updated", "entry": entry}
