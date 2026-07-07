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

    # Minutes to reuse cached odds before spending API credits on a fresh scan.
    odds_cache_ttl_minutes: int = 30

    # Max sportsbooks leagues fetched per live scan (1 credit each). 0 = no cap.
    odds_max_sports_per_scan: int = 12

    # priority = US majors + top soccer/tennis only; full = every active game sport.
    odds_scan_scope: str = "priority"

    environment: str = "development"
    default_user_id: str = ""

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


settings = Settings()


def reload_settings() -> Settings:
    """Re-read .env — use after updating API keys without restarting uvicorn."""
    global settings
    settings = Settings()
    return settings
