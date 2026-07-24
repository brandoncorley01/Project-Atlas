"""Market & Options Intelligence API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.db.supabase_client import SupabaseClient
from app.dependencies import get_access_token, get_current_user_id
from app.market_intelligence.service import MarketIntelligenceService

router = APIRouter()


def _svc(user_id: str, token: str) -> MarketIntelligenceService:
    return MarketIntelligenceService(SupabaseClient(token), user_id)


def _require_enabled() -> None:
    if not getattr(settings, "atlas_market_intelligence_enabled", True):
        raise HTTPException(status_code=404, detail="Market intelligence is disabled")


class LowPremiumFilterBody(BaseModel):
    max_contract_price: float = Field(default=5.0, gt=0, le=50)
    max_position_risk: float = Field(default=500.0, gt=0)
    option_type: str | None = Field(default=None, pattern="^(call|put)$")
    min_dte: int = Field(default=7, ge=1, le=365)
    max_dte: int = Field(default=45, ge=1, le=730)
    min_open_interest: int = Field(default=200, ge=0)
    min_volume: int = Field(default=100, ge=0)
    max_spread_pct: float = Field(default=12.0, gt=0, le=100)
    min_unusual_score: float = Field(default=55.0, ge=0, le=100)
    min_confidence: float = Field(default=45.0, ge=0, le=100)
    min_delta: float | None = Field(default=0.20, ge=0, le=1)
    max_otm_pct: float = Field(default=0.12, ge=0, le=1)
    require_catalyst: bool = False


class PositionEvalBody(BaseModel):
    position_key: str | None = None
    symbol: str
    module: str = "stock"
    return_pct: float | None = None
    momentum_score: float | None = Field(default=None, ge=-1, le=1)
    trend_ok: bool | None = None
    relative_volume: float | None = None
    options_support: float | None = Field(default=None, ge=-1, le=1)
    sector_support: float | None = Field(default=None, ge=-1, le=1)
    market_support: float | None = Field(default=None, ge=-1, le=1)
    thesis_valid: bool | None = True
    reward_risk: float | None = None
    days_to_event: float | None = None
    iv_crush: bool | None = None
    at_first_target: bool | None = None
    time_in_trade_days: float | None = None
    position_value: float | None = None
    capital_at_risk: float | None = None
    sector: str | None = None
    data_status: str = "partial"


class PortfolioExitBody(BaseModel):
    positions: list[PositionEvalBody] | None = None


@router.get("/status")
async def status(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    return await _svc(user_id, token).provider_status()


@router.get("/options/flow")
async def options_flow(
    limit: int = Query(default=50, ge=1, le=200),
    underlying: str | None = None,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).flow_scanner(limit=limit, underlying=underlying)


@router.post("/options/low-premium")
async def low_premium(
    body: LowPremiumFilterBody | None = None,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    filters = body.model_dump(exclude_none=True) if body else None
    return await _svc(user_id, token).low_premium(filters)


@router.get("/options/smart-money")
async def smart_money(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).smart_money()


@router.get("/options/heatmap")
async def options_heatmap(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).options_heatmap()


@router.get("/options/signals/history")
async def signal_history(
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).signal_history(limit=limit)


@router.get("/options/performance")
async def options_performance(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).performance_analytics()


@router.get("/options/alerts/settings")
async def alert_settings(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).alert_settings()


@router.get("/heatmap")
async def market_heatmap(
    size_by: str = Query(default="market_cap"),
    color_by: str = Query(default="daily_return"),
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).market_heatmap(size_by=size_by, color_by=color_by)


@router.get("/sector-rotation")
async def sector_rotation(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).sector_rotation()


@router.get("/smart-money-heatmap")
async def smart_money_heatmap(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).smart_money_heatmap()


@router.get("/weather")
async def market_weather(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).market_weather()


@router.get("/replay")
async def historical_replay(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).historical_replay()


@router.post("/exit/evaluate")
async def evaluate_exit(
    body: PositionEvalBody,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    return await _svc(user_id, token).evaluate_position(body.model_dump())


@router.post("/exit/portfolio-heatmap")
async def portfolio_exit_heatmap(
    body: PortfolioExitBody | None = None,
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
) -> dict:
    _require_enabled()
    positions = None
    if body and body.positions:
        positions = [p.model_dump() for p in body.positions]
    return await _svc(user_id, token).portfolio_exit_heatmap(positions)
