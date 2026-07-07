from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.calibration_service import CalibrationService
from app.services.performance_service import PerformanceService

router = APIRouter()


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
) -> dict:
    service = PerformanceService(SupabaseClient(token), user_id)
    return await service.get_history(limit=limit, offset=offset, module=module)


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
    service = PerformanceService(SupabaseClient(token), user_id)
    try:
        entry = await service.log_outcome(
            module=module,
            signal_id=signal_id,
            outcome=outcome,
            return_pct=float(return_pct) if return_pct is not None else None,
            hold_duration_hours=float(hold_hours) if hold_hours is not None else None,
            resolution_source=resolution_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "logged", "entry": entry}
