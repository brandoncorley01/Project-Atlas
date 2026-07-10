"""Sports intelligence API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user, get_current_user_id
from app.services.signal_service import SignalService
from app.sports_intelligence.service import SportsIntelligenceService

router = APIRouter()


def _intel_service(user_id: str, token: str) -> SportsIntelligenceService:
    return SportsIntelligenceService(SupabaseClient(token), user_id)


def _require_enabled() -> None:
    if not settings.is_intelligence_enabled():
        raise HTTPException(status_code=404, detail="Sports intelligence layer is disabled")


async def _get_signal(user_id: str, token: str, signal_id: str) -> dict[str, Any]:
    row = await SignalService(SupabaseClient(token), user_id).get_sports(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Sports signal not found")
    return row


async def _require_admin(user: dict) -> None:
    owner = (settings.default_user_id or "").strip()
    if owner and user.get("user_id") == owner:
        return
    if settings.environment == "development":
        return
    raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/sports/intelligence/status")
async def intelligence_status() -> dict:
    return {"enabled": settings.is_intelligence_enabled()}


class ManualIntelligenceEntry(BaseModel):
    signal_id: str
    event_id: str | None = None
    source: str | None = None
    analyst: str | None = None
    source_url: str | None = None
    market_type: str | None = None
    selection: str
    line: float | None = None
    odds: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=100)
    supporting_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    summary: str | None = None
    published_at: str | None = None


@router.get("/sports/{signal_id}/intelligence")
async def get_sports_intelligence(
    signal_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    signal = await _get_signal(user_id, token, signal_id)
    payload = await _intel_service(user_id, token).get_intelligence_payload(signal)
    if payload is None:
        raise HTTPException(status_code=404, detail="Sports intelligence layer is disabled")
    return payload


@router.post("/sports/{signal_id}/intelligence/refresh")
async def refresh_sports_intelligence(
    signal_id: str,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    signal = await _get_signal(user_id, token, signal_id)
    return await _intel_service(user_id, token).refresh_signal_intelligence(signal)


@router.post("/sports/intelligence/manual")
async def create_manual_intelligence(
    entry: ManualIntelligenceEntry,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    _require_enabled()
    await _require_admin(user)
    service = _intel_service(user["user_id"], user["access_token"])
    row = await service.add_manual_entry(entry.model_dump())
    if not row:
        raise HTTPException(status_code=400, detail="Could not save manual entry")
    return {"item": row}


@router.delete("/sports/intelligence/manual/{item_id}")
async def delete_manual_intelligence(
    item_id: str,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    _require_enabled()
    await _require_admin(user)
    ok = await _intel_service(user["user_id"], user["access_token"]).delete_manual_entry(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True}


@router.get("/sports/intelligence/diagnostics")
async def intelligence_diagnostics(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    _require_enabled()
    await _require_admin(user)
    return await _intel_service(user["user_id"], user["access_token"]).diagnostics()
