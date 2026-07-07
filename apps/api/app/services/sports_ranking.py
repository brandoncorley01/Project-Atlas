"""Near-term prioritization and display ranking for sports signals."""

from __future__ import annotations

from typing import Any

from app.services.freshness import hours_until_event

NEAR_TERM_HOURS = 48
SOON_HOURS = 24
MAX_SCAN_HORIZON_HOURS = 168
STRONG_NEWS_MIN_SCORE = 4.0


def hours_to_start(row: dict[str, Any]) -> float | None:
    return hours_until_event(row.get("event_start"))


def is_near_term(row: dict[str, Any], *, max_hours: float = NEAR_TERM_HOURS) -> bool:
    hours = hours_to_start(row)
    return hours is not None and 0 < hours <= max_hours


def is_within_horizon(row: dict[str, Any], *, max_hours: float = MAX_SCAN_HORIZON_HOURS) -> bool:
    hours = hours_to_start(row)
    return hours is not None and 0 < hours <= max_hours


def timing_tier(row: dict[str, Any]) -> str:
    hours = hours_to_start(row)
    if hours is None or hours <= 0:
        return "past"
    if hours <= SOON_HOURS:
        return "live_soon"
    if hours <= NEAR_TERM_HOURS:
        return "today"
    if hours <= MAX_SCAN_HORIZON_HOURS:
        return "this_week"
    return "later"


def timing_boost(hours: float | None) -> float:
    if hours is None:
        return -20.0
    if hours <= 6:
        return 14.0
    if hours <= SOON_HOURS:
        return 12.0
    if hours <= NEAR_TERM_HOURS:
        return 8.0
    if hours <= 72:
        return 1.0
    return -8.0


def composite_score(row: dict[str, Any]) -> float:
    opp = float(row.get("opportunity_score") or 0)
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    edge = float(snap.get("edge_pct") or lm.get("edge_pct") or 0)
    hours = hours_to_start(row)
    boost = timing_boost(hours)
    soon_penalty = 0.0
    if hours is not None and hours > NEAR_TERM_HOURS:
        soon_penalty = min(25.0, (hours - NEAR_TERM_HOURS) * 0.15)
    stats_support = float(snap.get("stats_support") or 0)
    return opp + boost + edge * 0.35 - soon_penalty + stats_support * 0.2


def sort_for_display(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            0 if is_near_term(r) else 1,
            -composite_score(r),
            hours_to_start(r) if hours_to_start(r) is not None else 9999,
        ),
    )


def sort_for_parlay_pool(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    near = [r for r in rows if is_near_term(r)]
    pool = near if len(near) >= 2 else [r for r in rows if is_within_horizon(r)]
    return sort_for_display(pool)


def filter_near_term(rows: list[dict[str, Any]], *, max_hours: float = NEAR_TERM_HOURS) -> list[dict[str, Any]]:
    return [r for r in rows if is_near_term(r, max_hours=max_hours)]
