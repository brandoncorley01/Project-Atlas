"""Near-term prioritization and display ranking for sports signals."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.freshness import hours_until_event, parse_iso

NEAR_TERM_HOURS = 48
SOON_HOURS = 24
WEEK_HOURS = 168
MONTH_HOURS = 720  # 30 days — longer-dated game lines
# Keep season-long futures and early lines (≈90 days). Championship outrights
# may sit further out and are allowed via is_within_horizon(..., futures=True).
MAX_SCAN_HORIZON_HOURS = 2160
STRONG_NEWS_MIN_SCORE = 4.0

# US sports slate day — "Today" parlays use Eastern calendar date.
ATLAS_SPORTS_TZ = ZoneInfo("America/New_York")


def hours_to_start(row: dict[str, Any]) -> float | None:
    return hours_until_event(row.get("event_start"))


def event_local_date(event_start: str | None, *, tz: ZoneInfo = ATLAS_SPORTS_TZ) -> date | None:
    parsed = parse_iso(event_start)
    if not parsed:
        return None
    return parsed.astimezone(tz).date()


def sports_today(*, tz: ZoneInfo = ATLAS_SPORTS_TZ) -> date:
    return datetime.now(tz).date()


def is_calendar_today(row: dict[str, Any], *, tz: ZoneInfo = ATLAS_SPORTS_TZ) -> bool:
    """True when the game kicks off later today (Eastern calendar day)."""
    hours = hours_to_start(row)
    if hours is None or hours <= 0:
        return False
    if is_futures_row(row):
        return False
    event_day = event_local_date(row.get("event_start"), tz=tz)
    return event_day is not None and event_day == sports_today(tz=tz)


def is_near_term(row: dict[str, Any], *, max_hours: float = NEAR_TERM_HOURS) -> bool:
    hours = hours_to_start(row)
    return hours is not None and 0 < hours <= max_hours


def is_futures_row(row: dict[str, Any]) -> bool:
    bet = str(row.get("bet_type") or "").lower()
    snap = row.get("scoring_snapshot") or {}
    return bet in {"futures", "outright"} or bool(snap.get("is_futures"))


def is_within_horizon(row: dict[str, Any], *, max_hours: float = MAX_SCAN_HORIZON_HOURS) -> bool:
    hours = hours_to_start(row)
    if hours is None or hours <= 0:
        return False
    # Championship futures often commence at the event date months out.
    if is_futures_row(row):
        return hours <= max(max_hours, 8760)  # up to ~1 year
    return hours <= max_hours


def timing_tier(row: dict[str, Any]) -> str:
    hours = hours_to_start(row)
    if hours is None or hours <= 0:
        return "past"
    if is_futures_row(row):
        return "futures"
    if is_calendar_today(row):
        return "calendar_today"
    if hours <= SOON_HOURS:
        return "live_soon"
    if hours <= NEAR_TERM_HOURS:
        return "next_48h"
    if hours <= WEEK_HOURS:
        return "this_week"
    if hours <= MONTH_HOURS:
        return "this_month"
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
        return 3.0
    if hours <= WEEK_HOURS:
        return 1.0
    if hours <= MONTH_HOURS:
        return 0.0
    # Longer-dated lines still rank on edge — mild penalty only.
    return -3.0


def composite_score(row: dict[str, Any]) -> float:
    opp = float(row.get("opportunity_score") or 0)
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    edge = float(snap.get("edge_pct") or lm.get("edge_pct") or 0)
    hours = hours_to_start(row)
    boost = timing_boost(hours)
    soon_penalty = 0.0
    if hours is not None and hours > NEAR_TERM_HOURS and not is_futures_row(row):
        # Soft penalty so future game lines remain visible when edge is strong.
        soon_penalty = min(12.0, (hours - NEAR_TERM_HOURS) * 0.04)
    stats_support = float(snap.get("stats_support") or 0)
    today_boost = 4.0 if is_calendar_today(row) else 0.0
    return opp + boost + edge * 0.35 - soon_penalty + stats_support * 0.2 + today_boost


def sort_for_display(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            0 if is_calendar_today(r) else (1 if is_near_term(r) else (2 if not is_futures_row(r) else 3)),
            -composite_score(r),
            hours_to_start(r) if hours_to_start(r) is not None else 9999,
        ),
    )


def market_family_key(row: dict[str, Any]) -> str:
    """One Atlas decision per event + bet type (never both sides of ML/spread/total)."""
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    event_id = snap.get("event_id") or lm.get("event_id") or row.get("event_name") or row.get("id") or ""
    bet_type = str(row.get("bet_type") or "moneyline").lower()
    return f"{event_id}|{bet_type}"


def dedupe_one_side_per_market(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest row per event+bet_type; drop contradicting alternate sides."""
    if len(rows) <= 1:
        return rows
    best_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = market_family_key(row)
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = row
            order.append(key)
            continue
        if composite_score(row) > composite_score(prev):
            best_by_key[key] = row
    return [best_by_key[k] for k in order if k in best_by_key]


def sort_for_parlay_pool(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = [r for r in rows if is_calendar_today(r)]
    if len(today) >= 2:
        near = [r for r in rows if is_near_term(r) and not is_calendar_today(r)]
        return sort_for_display(today + near)
    near = [r for r in rows if is_near_term(r)]
    pool = near if len(near) >= 2 else [r for r in rows if is_within_horizon(r) and not is_futures_row(r)]
    return sort_for_display(pool)


def filter_near_term(rows: list[dict[str, Any]], *, max_hours: float = NEAR_TERM_HOURS) -> list[dict[str, Any]]:
    return [r for r in rows if is_near_term(r, max_hours=max_hours)]


def filter_calendar_today(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if is_calendar_today(r)]
