"""Tests for structured dashboard load warnings."""

from app.services.dashboard_warnings import (
    append_warning,
    load_status_for,
    make_warning,
    warning_summary,
)


def test_soft_issues_are_not_partial():
    warnings: list[dict] = []
    append_warning(warnings, "atlas_briefing", detail="timed out (template only)")
    append_warning(warnings, "resolve_outcomes", detail="timed out (skipped)")
    append_warning(warnings, "news_auto_refresh", detail="boom")
    append_warning(warnings, "breaking_news", detail="db")
    append_warning(warnings, "list_parlays", detail="db")
    append_warning(warnings, "performance_summary", detail="db")
    assert load_status_for(warnings) == "ok"
    assert warning_summary(warnings)["error"] == 0


def test_critical_opportunity_failure_is_partial():
    warnings: list[dict] = []
    append_warning(warnings, "sports_opportunities", detail="connection reset")
    assert load_status_for(warnings) == "partial"
    assert warnings[0]["severity"] == "error"
    assert warnings[0]["repair"] == "sports"
    assert "Fix all" in warnings[0]["fix"] or "Sports" in warnings[0]["fix"]


def test_make_warning_unknown_code_defaults_to_info():
    w = make_warning("custom_thing", detail="boom")
    assert w["severity"] == "info"
    assert w["code"] == "custom_thing"
    assert w["detail"] == "boom"
    assert "Fix all" in w["fix"]
