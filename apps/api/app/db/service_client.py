"""Supabase client using the service role / secret key — for cron jobs and writes."""

from __future__ import annotations

import base64
import json
import logging

from fastapi import HTTPException, status

from app.config import settings
from app.db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


def _jwt_role(token: str) -> str | None:
    """Read the unverified JWT role claim (legacy Supabase keys are JWTs)."""
    try:
        parts = (token or "").split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        role = data.get("role")
        return str(role) if role else None
    except Exception:
        return None


def is_opaque_secret_key(key: str) -> bool:
    """New Supabase secret keys look like sb_secret_… (not JWTs)."""
    return (key or "").strip().startswith("sb_secret_")


def is_opaque_publishable_key(key: str) -> bool:
    return (key or "").strip().startswith("sb_publishable_")


def is_real_service_role_key(key: str | None = None) -> bool:
    """True for a privileged backend key (legacy service_role JWT or sb_secret_)."""
    raw = (key if key is not None else settings.supabase_service_role_key or "").strip()
    if not raw:
        return False
    anon = (settings.supabase_anon_key or "").strip()
    if anon and raw == anon:
        return False
    if is_opaque_publishable_key(raw):
        return False
    if is_opaque_secret_key(raw):
        return True
    return _jwt_role(raw) == "service_role"


def get_service_db() -> SupabaseClient:
    key = (settings.supabase_service_role_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_SERVICE_ROLE_KEY is not configured",
        )
    if not is_real_service_role_key(key):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SUPABASE_SERVICE_ROLE_KEY is missing or set to the anon/publishable key. "
                "Paste the Secret key (sb_secret_…) from Supabase → Settings → API Keys, "
                "or the legacy service_role JWT from the Legacy API keys tab."
            ),
        )
    client = SupabaseClient(key)
    # Privileged key must be the apikey. Opaque sb_secret_ keys must NOT also be
    # sent as Authorization Bearer — Supabase rejects that with Invalid JWT.
    client.headers["apikey"] = key
    if is_opaque_secret_key(key):
        client.headers.pop("Authorization", None)
    else:
        client.headers["Authorization"] = f"Bearer {key}"
    return client


def get_write_db(user_access_token: str) -> SupabaseClient:
    """DB client for authenticated writes.

    Prefer the real service/secret key (bypasses RLS after the request already verified the user).
    Fall back to the caller's JWT when the service key is missing/misconfigured.
    """
    if is_real_service_role_key():
        try:
            return get_service_db()
        except HTTPException:
            logger.warning("Service-role write client unavailable — using user JWT")
    token = (user_access_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token for database write",
        )
    return SupabaseClient(token)
