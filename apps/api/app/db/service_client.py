"""Supabase client using the service role key — for cron jobs and internal tasks."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.config import settings
from app.db.supabase_client import SupabaseClient


def get_service_db() -> SupabaseClient:
    key = (settings.supabase_service_role_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_SERVICE_ROLE_KEY is not configured",
        )
    return SupabaseClient(key)
