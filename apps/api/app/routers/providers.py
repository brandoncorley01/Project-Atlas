from fastapi import APIRouter

from app.config import reload_settings

router = APIRouter()


@router.get("/providers/status")
async def providers_status(refresh: bool = False) -> dict:
    """Show which data providers are configured."""
    reload_settings()
    from app.config import settings as active_settings

    finnhub_configured = bool(active_settings.finnhub_api_key)
    finnhub_connected = False
    finnhub_error: str | None = None

    if finnhub_configured:
        try:
            from app.providers.stocks.finnhub import FinnhubClient

            client = FinnhubClient()
            quote = await client.get_quote("AAPL")
            finnhub_connected = float(quote.get("c") or 0) > 0
        except Exception as exc:
            finnhub_error = str(exc)

    odds_configured = bool(active_settings.odds_api_keys)
    odds_connected = False
    odds_error: str | None = None
    odds_requests_remaining: str | None = None
    odds_requests_used: str | None = None
    odds_quota_exhausted = False
    odds_key_count = len(active_settings.odds_api_keys)
    odds_total_remaining: int | None = None
    odds_keys_breakdown: list[dict] = []
    odds_active_key_index: int | None = None

    from app.providers.sports.odds_api import (
        estimate_live_scan_credits,
        odds_cache_status,
        probe_all_odds_keys,
    )

    cache_status = odds_cache_status()
    odds_cache_has_data = cache_status["has_data"]
    odds_cache_age_minutes = cache_status["age_minutes"]
    odds_cache_fresh = cache_status["fresh"]

    if odds_configured:
        try:
            probe = await probe_all_odds_keys(use_cache=not refresh)
            odds_key_count = probe.get("key_count") or odds_key_count
            odds_keys_breakdown = probe.get("keys") or []
            odds_total_remaining = probe.get("total_remaining")
            odds_active_key_index = probe.get("active_key_index")
            odds_quota_exhausted = bool(probe.get("quota_exhausted"))

            active_client = probe.get("active_client")
            if active_client is not None:
                odds_connected = True
                # Active key only — UI uses total_remaining (all keys summed)
                odds_requests_remaining = str(probe.get("total_remaining") or active_client.requests_remaining or "")
                odds_requests_used = active_client.requests_used
            elif odds_cache_has_data:
                odds_connected = True
                if odds_quota_exhausted:
                    odds_error = (
                        "All API keys out of credits — serving last-known cached odds. "
                        "Failover keys are configured; wait for monthly reset or add another key."
                    )
            else:
                err = probe.get("error")
                if err and "INVALID_KEY" in str(err):
                    odds_error = (
                        "API key rejected. Copy from the-odds-api.com into ODDS_API_KEY in apps/api/.env."
                    )
                elif odds_quota_exhausted:
                    odds_error = (
                        "All API keys out of monthly credits. Wait for reset or add another free key."
                    )
                elif err:
                    odds_error = str(err)[:200]
        except Exception as exc:
            msg = str(exc)
            odds_error = msg
            if "INVALID_KEY" in msg:
                odds_error = (
                    "API key rejected by The Odds API. "
                    "Copy the key from the-odds-api.com into ODDS_API_KEY in apps/api/.env, then restart the API."
                )
            elif "OUT_OF_USAGE_CREDITS" in msg or "quota" in msg.lower():
                odds_quota_exhausted = True

    estimated_scan_credits = estimate_live_scan_credits() if odds_configured else 0
    monthly_capacity = odds_key_count * 500 if odds_key_count else 500

    openai_configured = bool(active_settings.openai_api_key)
    openai_connected = False
    openai_error: str | None = None
    openai_model = active_settings.openai_model if openai_configured else None

    if openai_configured:
        if refresh:
            from app.services.llm_service import llm_service

            openai_connected, openai_error = await llm_service.probe_connection()
        else:
            openai_connected = True

    return {
        "finnhub": {
            "configured": finnhub_configured,
            "connected": finnhub_connected,
            "error": finnhub_error,
            "features": ["stock quotes", "RSI / trend", "relative volume", "company news catalysts"],
        },
        "odds_api": {
            "configured": odds_configured,
            "connected": odds_connected,
            "quota_exhausted": odds_quota_exhausted,
            "key_count": odds_key_count,
            "active_key_index": odds_active_key_index,
            "keys": odds_keys_breakdown,
            "total_remaining": odds_total_remaining,
            "monthly_capacity": monthly_capacity,
            "requests_remaining": odds_requests_remaining,
            "requests_used": odds_requests_used,
            "cache_has_data": odds_cache_has_data,
            "cache_has_events": cache_status.get("cache_has_events"),
            "cache_within_ttl": cache_status.get("cache_within_ttl"),
            "cache_rescore_free": cache_status.get("cache_rescore_free"),
            "cache_age_minutes": odds_cache_age_minutes,
            "cache_fetched_at": cache_status.get("fetched_at"),
            "cache_fresh": odds_cache_fresh,
            "cache_needs_live_refresh": cache_status.get("cache_needs_live_refresh"),
            "near_term_leagues": cache_status.get("near_term_leagues") or [],
            "league_catalog": cache_status.get("league_catalog") or [],
            "near_term_event_count": cache_status.get("near_term_event_count"),
            "cache_ttl_minutes": active_settings.odds_cache_ttl_minutes,
            "minutes_until_stale": cache_status.get("minutes_until_stale"),
            "scan_scope": active_settings.odds_scan_scope,
            "max_sports_per_scan": active_settings.odds_max_sports_per_scan,
            "estimated_live_scan_credits": estimated_scan_credits,
            "spend_locked": bool(cache_status.get("spend_locked")),
            "odds_spend_mode": cache_status.get("odds_spend_mode")
            or active_settings.odds_spend_mode_normalized(),
            # Explicit Fetch stays available even when auto-spend is cache-only.
            "live_fetch_allowed": active_settings.odds_explicit_fetch_allowed(),
            "auto_spend_allowed": active_settings.odds_live_spending_allowed(),
            "error": odds_error,
            "features": [
                "multi-key failover",
                "response cache",
                "cache-only auto-spend lock",
                "explicit Fetch live odds",
                "US-core live scan (when unlocked)",
                "FanDuel / DraftKings lines",
                "zero-credit rescore",
                "OpenAI slate ranking",
                "credit guard",
                "moneyline / spread / totals",
                "+EV edge scan",
            ],
        },
        "options_data": {
            "provider": "yahoo_finance",
            "requires_key": False,
        },
        "openai": {
            "configured": openai_configured,
            "connected": openai_connected and openai_configured,
            "model": openai_model,
            "error": openai_error,
            "features": [
                "auto-track every scan pick",
                "daily Atlas briefing",
                "market intelligence narratives",
                "coach insight narratives",
                "deeper pick explanations",
            ],
        },
    }
