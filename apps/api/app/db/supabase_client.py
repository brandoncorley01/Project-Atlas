from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.db.http_client import get_http_client


def _sanitize_header_value(value: str | None, *, name: str = "header") -> str:
    """Strip whitespace/control chars — httpx raises Illegal header value otherwise."""
    if value is None:
        return ""
    cleaned = "".join(ch for ch in str(value) if 32 <= ord(ch) <= 126).strip()
    if value and not cleaned:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid {name} value (empty after sanitizing). Check API env keys.",
        )
    return cleaned


class SupabaseClient:
    def __init__(self, access_token: str) -> None:
        self.base_url = f"{_sanitize_header_value(settings.supabase_url, name='SUPABASE_URL').rstrip('/')}/rest/v1"
        token = _sanitize_header_value(access_token, name="access token")
        apikey = _sanitize_header_value(settings.supabase_anon_key, name="SUPABASE_ANON_KEY")
        self.access_token = token
        self.headers = {
            "apikey": apikey,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def set_privileged_key(self, key: str, *, opaque_secret: bool = False) -> None:
        """Use service_role JWT or sb_secret_ for writes that bypass RLS."""
        cleaned = _sanitize_header_value(key, name="SUPABASE_SERVICE_ROLE_KEY")
        self.headers["apikey"] = cleaned
        if opaque_secret:
            # New sb_secret_ keys must not go on Authorization (Invalid JWT).
            self.headers.pop("Authorization", None)
        else:
            self.headers["Authorization"] = f"Bearer {cleaned}"

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> Any:
        url = f"{self.base_url}/{table}"
        # Re-sanitize every request in case callers mutated headers.
        safe_headers = {
            k: _sanitize_header_value(v, name=k) if isinstance(v, str) else v
            for k, v in self.headers.items()
        }
        try:
            client = get_http_client()
            response = await client.request(
                method, url, headers=safe_headers, params=params, json=json
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

    async def upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        url_headers = {
            **{
                k: _sanitize_header_value(v, name=k) if isinstance(v, str) else v
                for k, v in self.headers.items()
            },
            "Prefer": "return=representation,resolution=merge-duplicates",
        }
        url = f"{self.base_url}/{table}"
        params: dict[str, str] = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        try:
            client = get_http_client()
            response = await client.request(
                "POST", url, headers=url_headers, params=params, json=rows
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
