"""Tests for structured dashboard load warnings."""

from app.services.dashboard_warnings import (
    append_warning,
    load_status_for,
    make_warning,
    warning_summary,
)


def test_news_success_is_not_a_catalog_warning():
    """Successful news refresh must not create a partial-load warning."""
    warnings: list[dict] = []
    # Intentionally do nothing on success — mirrors dashboard.py.
    assert load_status_for(warnings) == "ok"
    assert warning_summary(warnings) == {"info": 0, "warn": 0, "error": 0}


def test_soft_timeout_is_info_not_partial():
    warnings: list[dict] = []
    append_warning(warnings, "atlas_briefing", detail="timed out (template only)")
    append_warning(warnings, "resolve_outcomes", detail="timed out (skipped)")
    assert load_status_for(warnings) == "ok"
    assert warning_summary(warnings)["info"] == 2
    assert warning_summary(warnings)["error"] == 0
    assert "fix" in warnings[0]
    assert warnings[0]["action"]["href"]


def test_critical_opportunity_failure_is_partial():
    warnings: list[dict] = []
    append_warning(warnings, "sports_opportunities", detail="connection reset")
    assert load_status_for(warnings) == "partial"
    assert warnings[0]["severity"] == "error"
    assert "Scan sports" in warnings[0]["fix"] or "Sports" in warnings[0]["fix"]
    assert warnings[0]["action"]["href"] == "/sports"
    assert warnings[0]["detail"] == "connection reset"


def test_make_warning_unknown_code_defaults_to_warn():
    w = make_warning("custom_thing", detail="boom")
    assert w["severity"] == "warn"
    assert w["code"] == "custom_thing"
    assert w["detail"] == "boom"
    assert w["fix"]
