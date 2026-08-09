import os
import re
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _API_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    cron_secret: str = "dev-cron-secret"

    finnhub_api_key: str = ""
    polygon_api_key: str = ""
    odds_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Minutes to reuse cached odds before spending API credits on a fresh scan.
    odds_cache_ttl_minutes: int = 360

    # Max sportsbooks leagues fetched per live scan (1 credit each).
    # Default 6 = useful US-core slate; 0 = no cap (expensive).
    odds_max_sports_per_scan: int = 6

    # priority = in-season majors only (credit-safe); full = every active game sport.
    odds_scan_scope: str = "priority"

    # Championship futures cost extra credits — off for routine Fetch live odds.
    odds_include_futures_on_live: bool = False

    # Refuse a live pull when remaining credits are below this + estimated scan cost.
    # Leave a small cushion so free-tier keys (~500/mo) aren't drained overnight.
    # Values >= 500 effectively block all live Fetch — keep this well below that.
    odds_min_credits_reserve: int = 25

    # Atlas Insight: max soon games to pull FanDuel player props for (each uses ~3 credits).
    # 0 = never spend Odds credits on Insight (use odds/props cache only).
    # User-initiated Insight may still spend when >0 even if ODDS_SPEND_MODE=cache_only.
    odds_insight_prop_events: int = 2

    # Keep a reserve so Insight prop pulls don't zero the free-tier quota.
    odds_insight_min_credits_reserve: int = 25

    # Search: max matching games to pull FanDuel/DK player props for (credit-capped).
    # 0 = Search uses cache + board only (no live prop pulls).
    # User-initiated Search may still live-seed game lines when cache misses.
    odds_search_prop_events: int = 2

    # Search prop pull reserve — leave credits for Fetch live.
    odds_search_min_credits_reserve: int = 25

    # cache_only = never call Odds live APIs (Rescore / Insight / Search from cache).
    # conservative = live only when remaining > reserve; no Insight/Search prop pulls.
    # normal = previous behavior.
    odds_spend_mode: str = "cache_only"

    environment: str = "development"
    default_user_id: str = ""

    # Sports Expert Intelligence Layer — analyst support under each pick
    atlas_expert_intelligence_enabled: bool = True
    atlas_intelligence_learning_mode: str = "observe"
    atlas_max_expert_confidence_adjustment: float = 8.0
    atlas_max_news_confidence_adjustment: float = 6.0
    atlas_max_total_intelligence_adjustment: float = 12.0

    # Kalshi public-probability pulse on sports cards (no API key; public trade API).
    atlas_kalshi_public_pulse_enabled: bool = True

    # Market & Options Intelligence
    atlas_market_intelligence_enabled: bool = True
    atlas_options_flow_provider: str = "yahoo_derived"
    atlas_options_flow_allow_simulated: bool = True
    atlas_exit_score_version: str = "exit_v1"
    atlas_options_score_version: str = "options_activity_v1"
    atlas_earnings_normal_risk_usd: float = 100.0
    atlas_earnings_paper_risk_usd: float = 100.0  # legacy alias
    atlas_earnings_micro_coattail_fraction: float = 0.18
    atlas_earnings_allow_fixture_fallback: bool = False
    atlas_earnings_allow_simulated: bool = False  # legacy alias

    def is_intelligence_enabled(self) -> bool:
        return bool(self.atlas_expert_intelligence_enabled)

    def is_market_intelligence_enabled(self) -> bool:
        return bool(self.atlas_market_intelligence_enabled)

    @model_validator(mode="after")
    def _platform_port(self) -> "Settings":
        """Render/Railway/Fly inject PORT — prefer it over API_PORT in .env."""
        port = os.environ.get("PORT")
        if port:
            try:
                self.api_port = int(port)
            except ValueError:
                pass
        return self

    @field_validator(
        "finnhub_api_key",
        "polygon_api_key",
        "odds_api_key",
        "openai_api_key",
        "supabase_anon_key",
        "supabase_service_role_key",
        "supabase_jwt_secret",
        "supabase_url",
        mode="before",
    )
    @classmethod
    def _strip_api_keys(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        # Drop CR/LF/control chars from pasted secrets (common .env / Render paste bug).
        return "".join(ch for ch in value if 32 <= ord(ch) <= 126).strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def odds_api_keys(self) -> list[str]:
        """Support multiple free Odds API keys (comma/space separated) for failover."""
        raw = (self.odds_api_key or "").strip()
        if not raw:
            return []
        seen: list[str] = []
        for part in re.split(r"[,\s]+", raw):
            key = part.strip()
            if key and key not in seen:
                seen.append(key)
        return seen

    def odds_spend_mode_normalized(self) -> str:
        mode = (self.odds_spend_mode or "cache_only").strip().lower()
        if mode in {"cache_only", "locked", "off", "zero"}:
            return "cache_only"
        if mode in {"conservative", "safe"}:
            return "conservative"
        return "normal"

    def odds_live_spending_allowed(self) -> bool:
        """False when automatic/background Odds API calls must not spend credits."""
        return self.odds_spend_mode_normalized() != "cache_only"

    def odds_explicit_fetch_allowed(self) -> bool:
        """User-initiated Fetch live odds may spend even when auto mode is cache_only."""
        return bool(self.odds_api_keys)

    def odds_intentional_live_allowed(self) -> bool:
        """User-initiated Search / Insight / cold-cache Scan may hit Odds APIs in cache_only.

        Warm-cache Rescore/Scan stay free. Callers must still honor credit
        reserves so free-tier keys aren't drained overnight.
        """
        return bool(self.odds_api_keys)


settings = Settings()


def reload_settings() -> Settings:
    """Re-read .env — use after updating API keys without restarting uvicorn."""
    global settings
    settings = Settings()
    return settings
