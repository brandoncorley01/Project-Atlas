"""Provider registry for options flow."""

from __future__ import annotations

from app.config import settings
from app.market_intelligence.providers.base import OptionsFlowProvider
from app.market_intelligence.providers.fixture import FixtureOptionsFlowProvider
from app.market_intelligence.providers.yahoo_derived import YahooDerivedFlowProvider


def get_options_flow_provider() -> OptionsFlowProvider:
    key = (getattr(settings, "atlas_options_flow_provider", None) or "fixture").strip().lower()
    allow_sim = bool(getattr(settings, "atlas_options_flow_allow_simulated", True))
    if key == "yahoo_derived":
        provider = YahooDerivedFlowProvider()
        if provider.is_enabled():
            return provider
        # Fall back to fixture only when allowed
        if allow_sim:
            return FixtureOptionsFlowProvider(allow=True)
        return provider
    return FixtureOptionsFlowProvider(allow=allow_sim or settings.environment == "development")


def list_provider_statuses() -> list[dict]:
    providers = [
        FixtureOptionsFlowProvider(allow=True),
        YahooDerivedFlowProvider(),
    ]
    active = get_options_flow_provider()
    out = []
    for p in providers:
        payload = p.status_payload()
        payload["active"] = p.id == active.id
        out.append(payload)
    return out
