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
    # Default 4 = MLB/WNBA-first US core (FanDuel/DraftKings); 0 = no cap (expensive).
    odds_max_sports_per_scan: int = 2

    # priority = in-season majors only (credit-safe); full = every active game sport.
    odds_scan_scope: str = "priority"

    # Championship futures cost extra credits — off for routine Fetch live odds.
    odds_include_futures_on_live: bool = False

    # Refuse a live pull when remaining credits are below this + estimated scan cost.
    odds_min_credits_reserve: int = 100

    # Atlas Insight: max soon games to pull FanDuel player props for (each uses ~3 credits).
    # 0 = never spend Odds credits on Insight (use odds/props cache only).
    odds_insight_prop_events: int = 0

    # Keep a reserve so Insight prop pulls don't zero the free-tier quota.
    odds_insight_min_credits_reserve: int = 100

    # Search: max matching games to pull FanDuel/DK player props for (credit-capped).
    # 0 = Search uses cache + OpenAI only (0 Odds credits).
    odds_search_prop_events: int = 0

    # Search prop pull reserve — leave credits for Fetch live.
    odds_search_min_credits_reserve: int = 100

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

    def is_intelligence_enabled(self) -> bool:
        return bool(self.atlas_expert_intelligence_enabled)

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
        mode="before",
    )
    @classmethod
    def _strip_api_keys(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

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
        """False when Atlas must not spend Odds API credits."""
        return self.odds_spend_mode_normalized() != "cache_only"


settings = Settings()


def reload_settings() -> Settings:
    """Re-read .env — use after updating API keys without restarting uvicorn."""
    global settings
    settings = Settings()
    return settings
