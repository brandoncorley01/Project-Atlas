import logging
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.http_client import get_http_client
from app.db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def _ensure_profile(user_id: str, email: str | None, token: str) -> None:
    """Create a missing profiles row (signup trigger may have failed)."""
    if not settings.supabase_url:
        return

    service_key = settings.supabase_service_role_key or settings.supabase_anon_key
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    base = f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles"

    try:
        client = get_http_client()
        check = await client.get(
            base,
            headers=headers,
            params={"id": f"eq.{user_id}", "select": "id", "limit": "1"},
        )
        if check.status_code == 200 and check.json():
            return

        insert = await client.post(
            base,
            headers=headers,
            json={"id": user_id, "email": email or ""},
        )
        if insert.status_code >= 400:
            # Fall back to user-scoped insert when service role is misconfigured.
            db = SupabaseClient(token.strip())
            rows = await db.select("profiles", filters={"id": f"eq.{user_id}"}, limit=1)
            if not rows:
                await db.insert("profiles", [{"id": user_id, "email": email or ""}])
    except Exception as exc:
        logger.warning("Profile bootstrap for %s: %s", user_id, exc)


async def _fetch_supabase_user(token: str) -> dict:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth is not configured (missing Supabase URL or anon key)",
        )

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    try:
        client = get_http_client()
        response = await client.get(
            url,
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {token}",
            },
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach Supabase auth: {exc}",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid auth response from Supabase",
        ) from exc


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    try:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = (credentials.credentials or "").strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = await _fetch_supabase_user(token)
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        await _ensure_profile(user_id, user.get("email"), token)

        return {
            "user_id": user_id,
            "email": user.get("email"),
            "role": user.get("role"),
            "access_token": token,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_current_user failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auth failed: {exc}",
        ) from exc


async def get_current_user_id(
    user: Annotated[dict, Depends(get_current_user)],
) -> str:
    return user["user_id"]


async def get_access_token(
    user: Annotated[dict, Depends(get_current_user)],
) -> str:
    return user["access_token"]
