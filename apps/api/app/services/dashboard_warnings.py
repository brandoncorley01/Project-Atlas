"""Structured dashboard load warnings with user-facing fix guidance."""

from __future__ import annotations

from typing import Any, Literal

Severity = Literal["info", "warn", "error"]

# Only core board load failures are error. Soft/secondary issues are info so
# Home never shows "partial load" unless opportunity loaders actually fail.
_CATALOG: dict[str, dict[str, Any]] = {
    "news_auto_refresh_timeout": {
        "severity": "info",
        "message": "News refresh timed out — using cached headlines.",
        "fix": "Tap Fix all, or open News and pull to refresh.",
        "action": {"label": "Open News", "href": "/news"},
        "repair": "news",
    },
    "news_auto_refresh": {
        "severity": "info",
        "message": "Could not refresh headlines for the briefing.",
        "fix": "Tap Fix all to refresh news, or open News.",
        "action": {"label": "Open News", "href": "/news"},
        "repair": "news",
    },
    "expire_stale": {
        "severity": "info",
        "message": "Cleanup of outdated plays was skipped.",
        "fix": "Tap Fix all to clean outdated plays.",
        "action": {"label": "Retry Home", "href": "/"},
        "repair": "maintain",
    },
    "signal_backfill": {
        "severity": "info",
        "message": "Performance tracking backfill was skipped.",
        "fix": "Tap Fix all to backfill tracking.",
        "action": {"label": "Open Performance", "href": "/performance"},
        "repair": "maintain",
    },
    "resolve_outcomes": {
        "severity": "info",
        "message": "Auto-grading was skipped.",
        "fix": "Tap Fix all to grade finished picks.",
        "action": {"label": "Open Performance", "href": "/performance"},
        "repair": "maintain",
    },
    "market_intelligence": {
        "severity": "info",
        "message": "Market Intelligence summary timed out.",
        "fix": "Open Market Intel, or tap Fix all and retry Home.",
        "action": {"label": "Open Market Intel", "href": "/market-intelligence"},
        "repair": "none",
    },
    "atlas_briefing": {
        "severity": "info",
        "message": "AI briefing fell back to a template summary.",
        "fix": "Tap Fix all (refreshes news), then Refresh on the briefing card.",
        "action": {"label": "Data providers", "href": "/#data-providers"},
        "repair": "news",
    },
    "top_opportunities": {
        "severity": "error",
        "message": "Options opportunities failed to load.",
        "fix": "Tap Fix all to rescan options, or open Options and scan.",
        "action": {"label": "Open Options", "href": "/options"},
        "repair": "options",
    },
    "budget_opportunities": {
        "severity": "error",
        "message": "Budget options failed to load.",
        "fix": "Tap Fix all to rescan options.",
        "action": {"label": "Open Options", "href": "/options"},
        "repair": "options",
    },
    "stock_opportunities": {
        "severity": "error",
        "message": "Stock swings failed to load.",
        "fix": "Tap Fix all to rescan stocks.",
        "action": {"label": "Open Stocks", "href": "/stocks"},
        "repair": "stocks",
    },
    "sports_opportunities": {
        "severity": "error",
        "message": "Sports plays failed to load.",
        "fix": "Tap Fix all to rescan sports odds.",
        "action": {"label": "Open Sports", "href": "/sports"},
        "repair": "sports",
    },
    "list_parlays": {
        "severity": "info",
        "message": "Featured parlay failed to load.",
        "fix": "Tap Fix all after a sports scan to rebuild parlays.",
        "action": {"label": "Open Parlays", "href": "/parlays"},
        "repair": "parlays",
    },
    "breaking_news": {
        "severity": "info",
        "message": "Breaking news failed to load.",
        "fix": "Tap Fix all to refresh news.",
        "action": {"label": "Open News", "href": "/news"},
        "repair": "news",
    },
    "briefing_news": {
        "severity": "info",
        "message": "Briefing headlines failed to load.",
        "fix": "Tap Fix all to refresh news.",
        "action": {"label": "Open News", "href": "/news"},
        "repair": "news",
    },
    "unread_alerts": {
        "severity": "info",
        "message": "Unread alert count failed to load.",
        "fix": "Open Alerts to see notifications.",
        "action": {"label": "Open Alerts", "href": "/alerts"},
        "repair": "none",
    },
    "performance_summary": {
        "severity": "info",
        "message": "Performance summary failed to load.",
        "fix": "Tap Fix all to grade/backfill, then open Performance.",
        "action": {"label": "Open Performance", "href": "/performance"},
        "repair": "maintain",
    },
    "tracking_stats": {
        "severity": "info",
        "message": "Tracking stats failed to load.",
        "fix": "Tap Fix all to backfill tracking.",
        "action": {"label": "Open Performance", "href": "/performance"},
        "repair": "maintain",
    },
    "catalyst_match": {
        "severity": "info",
        "message": "Live news catalysts could not be matched to plays.",
        "fix": "Opportunities still loaded. Tap Fix all to refresh news.",
        "action": {"label": "Open News", "href": "/news"},
        "repair": "news",
    },
}


def make_warning(
    code: str,
    *,
    detail: str | None = None,
    severity: Severity | None = None,
    message: str | None = None,
    fix: str | None = None,
    action: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a structured warning. Unknown codes default to info (not partial load)."""
    catalog = _CATALOG.get(code, {})
    text = message or catalog.get("message") or code.replace("_", " ")
    detail_clean = detail.strip() if detail else None

    out: dict[str, Any] = {
        "code": code,
        "severity": severity or catalog.get("severity") or "info",
        "message": text,
        "fix": fix
        or catalog.get("fix")
        or "Tap Fix all on Home. If this keeps happening, check Data providers.",
        "repair": catalog.get("repair") or "none",
    }
    act = action if action is not None else catalog.get("action")
    if act:
        out["action"] = act
    if detail_clean:
        out["detail"] = detail_clean
    return out


def append_warning(warnings: list[dict[str, Any]], code: str, **kwargs: Any) -> None:
    warnings.append(make_warning(code, **kwargs))


def load_status_for(warnings: list[dict[str, Any]]) -> str:
    """ok | partial — partial only when core board loaders fail (error)."""
    for w in warnings:
        if w.get("severity") == "error":
            return "partial"
    return "ok"


def warning_summary(warnings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"info": 0, "warn": 0, "error": 0}
    for w in warnings:
        sev = str(w.get("severity") or "info")
        if sev in counts:
            counts[sev] += 1
        else:
            counts["info"] += 1
    return counts
