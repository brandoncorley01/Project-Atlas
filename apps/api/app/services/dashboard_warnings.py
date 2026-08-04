"""Structured dashboard load warnings with user-facing fix guidance."""

from __future__ import annotations

from typing import Any, Literal

Severity = Literal["info", "warn", "error"]

# Codes that count toward "partial load" (warn/error only — never info).
_CATALOG: dict[str, dict[str, Any]] = {
    "news_auto_refresh_timeout": {
        "severity": "info",
        "message": "News refresh timed out — using cached headlines.",
        "fix": "Pull to refresh Home, or open News and wait a few seconds.",
        "action": {"label": "Open News", "href": "/news"},
    },
    "news_auto_refresh": {
        "severity": "warn",
        "message": "Could not refresh headlines for the briefing.",
        "fix": "Open News and pull to refresh. If this keeps happening, check RSS/news providers under Data providers.",
        "action": {"label": "Open News", "href": "/news"},
    },
    "expire_stale": {
        "severity": "info",
        "message": "Cleanup of outdated plays timed out — skipped this pass.",
        "fix": "Home still loaded. Pull to refresh; outdated plays may linger briefly.",
        "action": {"label": "Retry Home", "href": "/"},
    },
    "signal_backfill": {
        "severity": "info",
        "message": "Performance tracking backfill timed out — skipped this pass.",
        "fix": "Open Performance later; grading still runs in the background.",
        "action": {"label": "Open Performance", "href": "/performance"},
    },
    "resolve_outcomes": {
        "severity": "info",
        "message": "Auto-grading timed out — skipped this pass.",
        "fix": "Open Performance and use Sync if results look stale.",
        "action": {"label": "Open Performance", "href": "/performance"},
    },
    "market_intelligence": {
        "severity": "info",
        "message": "Market Intelligence summary timed out.",
        "fix": "Open Market Intel for the full view, or retry Home.",
        "action": {"label": "Open Market Intel", "href": "/market-intelligence"},
    },
    "atlas_briefing": {
        "severity": "info",
        "message": "AI briefing timed out — showing a template summary.",
        "fix": "Tap Refresh on the briefing card. If this persists, check OpenAI under Data providers.",
        "action": {"label": "Data providers", "href": "/#data-providers"},
    },
    "top_opportunities": {
        "severity": "error",
        "message": "Options opportunities failed to load.",
        "fix": "Retry Home. If empty, run Options from the scanner bar.",
        "action": {"label": "Open Options", "href": "/options"},
    },
    "budget_opportunities": {
        "severity": "error",
        "message": "Budget options failed to load.",
        "fix": "Retry Home, then run a deep Options scan.",
        "action": {"label": "Open Options", "href": "/options"},
    },
    "stock_opportunities": {
        "severity": "error",
        "message": "Stock swings failed to load.",
        "fix": "Retry Home. If empty, run Stocks → Scan stock swings.",
        "action": {"label": "Open Stocks", "href": "/stocks"},
    },
    "sports_opportunities": {
        "severity": "error",
        "message": "Sports plays failed to load.",
        "fix": "Retry Home. If empty, open Sports and Scan sports odds.",
        "action": {"label": "Open Sports", "href": "/sports"},
    },
    "list_parlays": {
        "severity": "warn",
        "message": "Featured parlay failed to load.",
        "fix": "Open Parlays and rebuild after a sports scan.",
        "action": {"label": "Open Parlays", "href": "/parlays"},
    },
    "breaking_news": {
        "severity": "warn",
        "message": "Breaking news failed to load.",
        "fix": "Open News and pull to refresh.",
        "action": {"label": "Open News", "href": "/news"},
    },
    "briefing_news": {
        "severity": "warn",
        "message": "Briefing headlines failed to load.",
        "fix": "Open News and pull to refresh.",
        "action": {"label": "Open News", "href": "/news"},
    },
    "unread_alerts": {
        "severity": "info",
        "message": "Unread alert count failed to load.",
        "fix": "Open Alerts to see notifications.",
        "action": {"label": "Open Alerts", "href": "/alerts"},
    },
    "performance_summary": {
        "severity": "warn",
        "message": "Performance summary failed to load.",
        "fix": "Open Performance and tap Sync if the board looks empty.",
        "action": {"label": "Open Performance", "href": "/performance"},
    },
    "tracking_stats": {
        "severity": "info",
        "message": "Tracking stats failed to load.",
        "fix": "Open Performance — tracking still updates in the background.",
        "action": {"label": "Open Performance", "href": "/performance"},
    },
    "catalyst_match": {
        "severity": "info",
        "message": "Live news catalysts could not be matched to plays.",
        "fix": "Opportunities still loaded. Open News for catalysts.",
        "action": {"label": "Open News", "href": "/news"},
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
    """Build a structured warning. Unknown codes default to warn severity."""
    catalog = _CATALOG.get(code, {})
    text = message or catalog.get("message") or code.replace("_", " ")
    if detail:
        detail_clean = detail.strip()
        # Keep the primary message human; attach technical detail separately.
        if detail_clean and detail_clean.lower() not in text.lower():
            pass
    else:
        detail_clean = None

    out: dict[str, Any] = {
        "code": code,
        "severity": severity or catalog.get("severity") or "warn",
        "message": text,
        "fix": fix or catalog.get("fix") or "Pull to refresh Home. If this keeps happening, check Data providers.",
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
    """ok | partial — partial only when warn/error issues exist."""
    for w in warnings:
        if w.get("severity") in {"warn", "error"}:
            return "partial"
    return "ok"


def warning_summary(warnings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"info": 0, "warn": 0, "error": 0}
    for w in warnings:
        sev = str(w.get("severity") or "warn")
        if sev in counts:
            counts[sev] += 1
        else:
            counts["warn"] += 1
    return counts
