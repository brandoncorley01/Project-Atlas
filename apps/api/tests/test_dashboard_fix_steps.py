"""Fix-all step ok handling and empty-board messaging."""

from __future__ import annotations

from app.services.dashboard_fix_service import _failed_step_summary, _step
import pytest


@pytest.mark.asyncio
async def test_step_preserves_coro_ok_false_and_sets_error():
    async def failing():
        return {"ok": False, "message": "No odds cache yet", "signals_created": 0}

    out = await _step("refresh_sports", failing())
    assert out["ok"] is False
    assert out["step"] == "refresh_sports"
    assert out["error"] == "No odds cache yet"


@pytest.mark.asyncio
async def test_step_marks_exception_as_failed():
    async def boom():
        raise RuntimeError("Load failed")

    out = await _step("refresh_news", boom())
    assert out["ok"] is False
    assert out["error"] == "Load failed"


def test_failed_step_summary_lists_errors():
    summary = _failed_step_summary(
        [
            {"step": "refresh_sports", "ok": False, "error": "No odds cache yet"},
            {"step": "expire_stale", "ok": True},
            {"step": "refresh_news", "ok": False, "message": "timeout"},
        ]
    )
    assert summary is not None
    assert "refresh_sports" in summary
    assert "No odds cache" in summary
    assert "refresh_news" in summary
