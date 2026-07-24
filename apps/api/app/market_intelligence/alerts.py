"""Alert helpers with dedup / cooldown semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


DEFAULT_ALERT_TYPES = [
    "unusual_options_signal",
    "repeated_directional_flow",
    "low_premium_opportunity",
    "sector_rotation",
    "market_weather_change",
    "exit_urgency_threshold",
    "thesis_invalidation",
    "iv_collapse",
    "liquidity_deterioration",
    "expiration_risk",
]


def default_alert_settings() -> list[dict[str, Any]]:
    return [
        {
            "alert_type": t,
            "enabled": t in ("unusual_options_signal", "exit_urgency_threshold", "market_weather_change"),
            "threshold": 70.0 if "urgency" in t or "unusual" in t else None,
            "cooldown_minutes": 60,
        }
        for t in DEFAULT_ALERT_TYPES
    ]


def should_send_alert(
    *,
    alert_type: str,
    dedup_key: str,
    last_sent_at: datetime | None,
    cooldown_minutes: int,
    data_status: str,
    allow_simulated: bool,
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = now or datetime.now(UTC)
    if data_status == "simulated" and not allow_simulated:
        return False, "simulated_blocked"
    if last_sent_at is not None:
        elapsed = now - (last_sent_at if last_sent_at.tzinfo else last_sent_at.replace(tzinfo=UTC))
        if elapsed < timedelta(minutes=cooldown_minutes):
            return False, "cooldown"
    return True, f"{alert_type}:{dedup_key}"
