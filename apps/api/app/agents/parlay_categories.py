"""Parlay time-window categories and freshness vs linked sports legs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.freshness import hours_until_event, is_sports_actionable, parse_iso
from app.services.sports_ranking import ATLAS_SPORTS_TZ, sports_today

NEAR_TERM_MAX_HOURS = 48
MULTI_DAY_SPAN_HOURS = 48

PARLAY_CATEGORY_ORDER = ("today", "next_48h", "multi_day")

PARLAY_CATEGORY_CATALOG: dict[str, dict[str, str]] = {
    "today": {
        "title": "Today",
        "short_label": "Today",
        "description": "Every leg kicks off today (US/Eastern) — same-day slate only.",
        "guide": (
            "Same-day parlays: all legs start on today's Eastern calendar date. "
            "Atlas builds up to six options per risk tier from today's sports picks only — "
            "ideal when you want the whole ticket to settle tonight."
        ),
    },
    "next_48h": {
        "title": "Next 24–48 Hours",
        "short_label": "24–48h",
        "description": "All legs kick off within the next 48 hours, spanning more than today.",
        "guide": (
            "Quick-turn parlays: every leg starts within 48 hours but not all on the same day. "
            "Atlas builds up to six options per risk tier ranked by edge, payout, and sport diversity."
        ),
    },
    "multi_day": {
        "title": "Multi-Day Stretch",
        "short_label": "Multi-day",
        "description": "Legs span more than 48 hours — the ticket plays out over several days.",
        "guide": (
            "Multi-day parlays span more than 48 hours between first and last kickoff — e.g. Saturday "
            "plus Monday Night Football. Atlas generates multiple tickets per risk tier so you can chase "
            "larger combined odds over a longer calendar window."
        ),
    },
}


def _normalize_signal_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _leg_event_start(leg: dict[str, Any], signal_map: dict[str, dict[str, Any]]) -> datetime | None:
    if leg.get("event_start"):
        return parse_iso(str(leg.get("event_start")))
    signal_id = _normalize_signal_id(leg.get("sports_signal_id"))
    if signal_id and signal_id in signal_map:
        return parse_iso(signal_map[signal_id].get("event_start"))
    return None


def _leg_starts(legs: list[dict[str, Any]], signal_map: dict[str, dict[str, Any]]) -> list[datetime]:
    starts: list[datetime] = []
    for leg in legs:
        parsed = _leg_event_start(leg, signal_map)
        if parsed is not None:
            starts.append(parsed)
    return starts


def is_parlay_actionable(
    legs: list[dict[str, Any]],
    signal_map: dict[str, dict[str, Any]],
) -> bool:
    """All legs must link to upcoming, active sports signals."""
    if not legs:
        return False
    for leg in legs:
        signal_id = _normalize_signal_id(leg.get("sports_signal_id"))
        if not signal_id:
            return False
        signal = signal_map.get(signal_id)
        if not signal:
            return False
        status = str(signal.get("status") or "active").lower()
        if status in ("expired", "cancelled", "settled"):
            return False
        if not is_sports_actionable(signal):
            return False
    return True


def _all_legs_today(starts: list[datetime]) -> bool:
    """True when every kickoff is later today on the Eastern sports calendar."""
    if not starts:
        return False
    today = sports_today(tz=ATLAS_SPORTS_TZ)
    now = datetime.now(UTC)
    dates = set()
    for start in starts:
        if (start - now).total_seconds() <= 0:
            return False
        local = start.astimezone(ATLAS_SPORTS_TZ).date()
        dates.add(local)
    return len(dates) == 1 and next(iter(dates)) == today


def compute_parlay_time_meta(
    legs: list[dict[str, Any]],
    signal_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    starts = _leg_starts(legs, signal_map)
    if not starts:
        return {
            "categories": [],
            "span_hours": None,
            "hours_to_first_leg": None,
            "hours_to_last_leg": None,
            "earliest_event_start": None,
            "latest_event_start": None,
        }

    now = datetime.now(UTC)
    earliest = min(starts)
    latest = max(starts)
    span_hours = (latest - earliest).total_seconds() / 3600
    hours_to_first = (earliest - now).total_seconds() / 3600
    hours_to_last = (latest - now).total_seconds() / 3600

    # Exclusive windows so Today / 24–48h / Multi-day sections don't duplicate tickets.
    categories: list[str] = []
    if _all_legs_today(starts):
        categories.append("today")
    elif hours_to_first > 0 and hours_to_last <= NEAR_TERM_MAX_HOURS:
        categories.append("next_48h")
    if span_hours > MULTI_DAY_SPAN_HOURS:
        categories.append("multi_day")

    return {
        "categories": categories,
        "span_hours": round(span_hours, 1),
        "hours_to_first_leg": round(hours_to_first, 1),
        "hours_to_last_leg": round(hours_to_last, 1),
        "earliest_event_start": earliest.isoformat(),
        "latest_event_start": latest.isoformat(),
    }


def categories_for_parlay(
    legs: list[dict[str, Any]],
    signal_map: dict[str, dict[str, Any]],
) -> list[str]:
    return compute_parlay_time_meta(legs, signal_map).get("categories") or []


def filter_parlays_by_category(
    parlays: list[dict[str, Any]],
    category: str,
) -> list[dict[str, Any]]:
    if category not in PARLAY_CATEGORY_CATALOG:
        return []
    return [p for p in parlays if category in (p.get("categories") or [])]


def category_counts(parlays: list[dict[str, Any]]) -> dict[str, int]:
    counts = {slug: 0 for slug in PARLAY_CATEGORY_ORDER}
    for parlay in parlays:
        for slug in parlay.get("categories") or []:
            if slug in counts:
                counts[slug] += 1
    return counts


def category_payload(slug: str, *, count: int = 0) -> dict[str, Any]:
    meta = PARLAY_CATEGORY_CATALOG.get(slug, {})
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "short_label": meta.get("short_label", slug),
        "description": meta.get("description", ""),
        "guide": meta.get("guide", ""),
        "count": count,
    }
