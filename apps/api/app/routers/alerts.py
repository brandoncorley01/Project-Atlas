from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.services.alert_service import AlertService

router = APIRouter()


@router.get("/alerts")
async def list_alerts(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    service = AlertService(SupabaseClient(token), user_id)
    return await service.list_alerts(unread_only=unread_only, limit=limit, offset=offset)


@router.patch("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = AlertService(SupabaseClient(token), user_id)
    row = await service.mark_read(alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return row


@router.post("/alerts/read-all")
async def mark_all_alerts_read(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    service = AlertService(SupabaseClient(token), user_id)
    count = await service.mark_all_read()
    return {"status": "ok", "marked_read": count}
