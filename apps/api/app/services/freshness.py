"""Signal freshness rules — hide obsolete plays and past events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

# Events must not have started (small grace for clock skew).
SPORTS_PRE_START_GRACE_MINUTES = 5

# Max age for market scans (hours since data_as_of).
STOCK_MAX_AGE_HOURS = 20
OPTIONS_MAX_AGE_HOURS = 20
PARLAY_MAX_AGE_HOURS = 12

# News older than this is dropped from feeds.
NEWS_MAX_AGE_HOURS = 72


def parse_iso(dt: str | None) -> datetime | None:
    if not dt:
        return None
    try:
        text = str(dt).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def age_hours(dt: str | None) -> float | None:
    parsed = parse_iso(dt)
    if not parsed:
        return None
    return (datetime.now(UTC) - parsed).total_seconds() / 3600


def hours_until_event(event_start: str | None) -> float | None:
    parsed = parse_iso(event_start)
    if not parsed:
        return None
    return (parsed - datetime.now(UTC)).total_seconds() / 3600


def is_sports_actionable(row: dict[str, Any]) -> bool:
    """True when the game hasn't started — used only for new scans, not listing saved picks."""
    hours = hours_until_event(row.get("event_start"))
    if hours is None:
        return False
    return hours > 0


def is_sports_listable(row: dict[str, Any]) -> bool:
    """True for any active saved pick with a known kickoff (including started games)."""
    return hours_until_event(row.get("event_start")) is not None


def is_event_upcoming(commence_time: str | None) -> bool:
    hours = hours_until_event(commence_time)
    return hours is not None and hours > 0


def filter_upcoming_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop finished games from odds payloads (cache or live)."""
    return [e for e in events if is_event_upcoming(e.get("commence_time"))]


def is_stock_fresh(row: dict[str, Any]) -> bool:
    scan_age = age_hours(row.get("data_as_of"))
    if scan_age is None:
        return False
    if scan_age > STOCK_MAX_AGE_HOURS:
        return False
    # On weekends the last session was Friday — hide weekday scans.
    now = datetime.now(UTC)
    if now.weekday() >= 5:
        scanned = parse_iso(row.get("data_as_of"))
        if scanned is None or scanned.weekday() < 5:
            return False
    return True


def is_options_fresh(row: dict[str, Any]) -> bool:
    expiration = parse_iso(row.get("expiration"))
    if expiration and datetime.now(UTC).date() > expiration.date():
        return False
    scan_age = age_hours(row.get("data_as_of"))
    if scan_age is None:
        return False
    return scan_age <= OPTIONS_MAX_AGE_HOURS


def is_parlay_fresh(row: dict[str, Any]) -> bool:
    scan_age = age_hours(row.get("data_as_of"))
    if scan_age is None:
        return False
    return scan_age <= PARLAY_MAX_AGE_HOURS


def is_news_fresh(row: dict[str, Any]) -> bool:
    pub_age = age_hours(row.get("published_at") or row.get("created_at"))
    if pub_age is None:
        return True
    return pub_age <= NEWS_MAX_AGE_HOURS


def sports_staleness_reason(row: dict[str, Any]) -> str | None:
    hours = hours_until_event(row.get("event_start"))
    if hours is not None and hours <= 0:
        return "Event has already started or finished"
    scan_age = age_hours(row.get("data_as_of"))
    if scan_age is not None and scan_age > 8:
        return f"Odds scan is {int(scan_age)}h old — refresh for current lines"
    return None


def stock_staleness_reason(row: dict[str, Any]) -> str | None:
    scan_age = age_hours(row.get("data_as_of"))
    if scan_age is not None and scan_age > STOCK_MAX_AGE_HOURS:
        return f"Setup is {int(scan_age)}h old — rescan for today's prices"
    return None


def format_data_as_of_label(dt: str | None) -> str | None:
    parsed = parse_iso(dt)
    if not parsed:
        return None
    local = parsed.astimezone()
    return local.strftime("%a %b %d, %H:%M")
