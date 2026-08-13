"""Durable Odds API cache in Supabase — survives Render ephemeral disk wipes.

Disk `.odds_cache.json` remains the hot L1 cache. This module is L2:
  - on disk miss → hydrate from odds_api_cache
  - on write → upsert odds_api_cache (best-effort)
  - on invalidate → delete remote row

Uses a short-lived sync httpx client so existing sync `_read_cache` / `_write_cache`
call sites do not need to become async.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.db.service_client import is_opaque_secret_key, is_real_service_role_key

logger = logging.getLogger(__name__)

CACHE_KEY = "default"
_TABLE = "odds_api_cache"


def _remote_enabled() -> bool:
    if not bool(getattr(settings, "odds_cache_remote", True)):
        return False
    key = (settings.supabase_service_role_key or "").strip()
    url = (settings.supabase_url or "").strip()
    return bool(url and key and is_real_service_role_key(key))


def _headers() -> dict[str, str]:
    key = (settings.supabase_service_role_key or "").strip()
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if not is_opaque_secret_key(key):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _rest_url() -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{_TABLE}"


def load_remote_cache() -> dict[str, Any] | None:
    """Load shared odds slate from Supabase. Returns disk-shaped payload or None."""
    if not _remote_enabled():
        return None
    try:
        with httpx.Client(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
            res = client.get(
                _rest_url(),
                headers=_headers(),
                params={
                    "cache_key": f"eq.{CACHE_KEY}",
                    "select": "fetched_at,stats,events,event_count",
                    "limit": "1",
                },
            )
        if res.status_code >= 400:
            logger.info("Odds remote cache read failed (%s): %s", res.status_code, res.text[:180])
            return None
        rows = res.json()
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        events = row.get("events")
        if not isinstance(events, list) or not events:
            return None
        fetched_at = row.get("fetched_at")
        if hasattr(fetched_at, "isoformat"):
            fetched_at = fetched_at.isoformat()
        stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
        return {
            "fetched_at": fetched_at,
            "events": events,
            "stats": {**stats, "remote_hydrated": True},
        }
    except Exception as exc:
        logger.info("Odds remote cache read skipped: %s", exc)
        return None


def save_remote_cache(payload: dict[str, Any], *, near_term_count: int | None = None) -> bool:
    """Upsert disk-shaped payload into odds_api_cache. Best-effort."""
    if not _remote_enabled():
        return False
    events = payload.get("events")
    if not isinstance(events, list):
        return False
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    fetched_at = payload.get("fetched_at") or datetime.now(UTC).isoformat()
    near = near_term_count if near_term_count is not None else len(events)

    body = {
        "cache_key": CACHE_KEY,
        "fetched_at": fetched_at,
        "event_count": len(events),
        "near_term_event_count": near,
        "stats": {k: v for k, v in stats.items() if k not in {"cached", "remote_hydrated"}},
        "events": events,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    try:
        headers = {
            **_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=4.0)) as client:
            res = client.post(
                _rest_url(),
                headers=headers,
                params={"on_conflict": "cache_key"},
                json=body,
            )
        if res.status_code >= 400:
            logger.info("Odds remote cache write failed (%s): %s", res.status_code, res.text[:180])
            return False
        return True
    except Exception as exc:
        logger.info("Odds remote cache write skipped: %s", exc)
        return False


def clear_remote_cache() -> None:
    if not _remote_enabled():
        return
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
            res = client.delete(
                _rest_url(),
                headers=_headers(),
                params={"cache_key": f"eq.{CACHE_KEY}"},
            )
        if res.status_code >= 400:
            logger.info("Odds remote cache clear failed (%s): %s", res.status_code, res.text[:120])
    except Exception as exc:
        logger.info("Odds remote cache clear skipped: %s", exc)


def remote_has_events() -> bool:
    """True when durable cache has any events (upcoming filter applied by caller)."""
    payload = load_remote_cache()
    return bool(payload and payload.get("events"))
