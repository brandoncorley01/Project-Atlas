from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.db.http_client import get_http_client


class SupabaseClient:
    def __init__(self, access_token: str) -> None:
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.access_token = access_token
        self.headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> Any:
        url = f"{self.base_url}/{table}"
        try:
            client = get_http_client()
            response = await client.request(
                method, url, headers=self.headers, params=params, json=json
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database unreachable: {exc}",
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Database error ({response.status_code}): {detail}",
            )

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid database response",
            ) from exc

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = await self._request("POST", table, json=rows)
        return result if isinstance(result, list) else [result]

    async def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)

        result = await self._request("GET", table, params=params)
        return result if isinstance(result, list) else []

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        await self._request("DELETE", table, params=filters)

    async def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
    ) -> list[dict[str, Any]]:
        result = await self._request("PATCH", table, params=filters, json=values)
        if result is None:
            return []
        return result if isinstance(result, list) else [result]

    async def upsert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        url_headers = {**self.headers, "Prefer": "return=representation,resolution=merge-duplicates"}
        url = f"{self.base_url}/{table}"
        try:
            client = get_http_client()
            response = await client.request(
                "POST", url, headers=url_headers, json=rows
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database unreachable: {exc}",
            ) from exc
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Database error ({response.status_code}): {response.text}",
            )
        result = response.json()
        return result if isinstance(result, list) else [result]


def explained_to_options_row(user_id: str, signal: Any) -> dict[str, Any]:
    from app.engine.models import ExplainedSignal

    assert isinstance(signal, ExplainedSignal)
    c = signal.planned.scored.candidate
    s = signal.planned.scored
    now = datetime.now(UTC).isoformat()

    return {
        "user_id": user_id,
        "underlying": c.symbol,
        "option_type": c.option_type,
        "strike": c.strike,
        "expiration": c.expiration.isoformat() if c.expiration else None,
        "days_to_expiration": c.days_to_expiration,
        "premium": c.premium,
        "bid": c.bid,
        "ask": c.ask,
        "bid_ask_spread_pct": round(c.bid_ask_spread_pct, 4),
        "volume": c.volume,
        "open_interest": c.open_interest,
        "delta": c.delta,
        "gamma": c.gamma,
        "theta": c.theta,
        "implied_volatility": c.implied_volatility,
        "entry_zone": signal.planned.entry_zone,
        "profit_targets": signal.planned.profit_targets,
        "max_loss": signal.planned.max_loss,
        "expected_hold_time": signal.planned.expected_hold_time,
        "confidence_score": s.confidence_score,
        "risk_score": s.risk_score,
        "opportunity_score": s.opportunity_score,
        "recommendation": signal.recommendation,
        "explanation": signal.explanation,
        "bull_case": signal.bull_case,
        "bear_case": signal.bear_case,
        "invalidation": signal.invalidation,
        "suggested_action": signal.suggested_action,
        "risk_warning": signal.risk_warning,
        "scoring_snapshot": s.scoring_snapshot,
        "status": "active",
        "data_as_of": now,
    }
