"""Options/Stocks scans — insert before delete, keep board on save failure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.stock_service import StockRefreshService


@pytest.mark.asyncio
async def test_refresh_stocks_keeps_board_when_insert_fails():
    db = MagicMock()
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock(side_effect=HTTPException(status_code=502, detail="Database error"))
    db.delete = AsyncMock()

    svc = StockRefreshService(db, "user-1")
    cal = MagicMock()
    cal.get_adjustments = AsyncMock(return_value={"stock_min_opportunity": 40})
    stale = MagicMock()
    stale.expire_all = AsyncMock()

    with (
        patch("app.services.calibration_service.CalibrationService", return_value=cal),
        patch("app.services.stale_signal_service.StaleSignalService", return_value=stale),
        patch.object(
            StockRefreshService,
            "build_universe",
            new=AsyncMock(return_value=(["AAA"], {"universe_size": 1})),
        ),
        patch.object(
            StockRefreshService,
            "_analyze_symbol",
            new=AsyncMock(
                return_value={
                    "user_id": "user-1",
                    "ticker": "AAA",
                    "opportunity_score": 72.0,
                    "status": "active",
                }
            ),
        ),
    ):
        result = await svc.refresh_stocks(replace=True, limit=10)

    assert result["ok"] is False
    assert result["signals_kept"] is True
    assert result["signals_created"] == 0
    assert "unchanged" in result["message"]
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_stocks_empty_scan_does_not_wipe_board():
    db = MagicMock()
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock()
    db.delete = AsyncMock()

    svc = StockRefreshService(db, "user-1")
    cal = MagicMock()
    cal.get_adjustments = AsyncMock(return_value={"stock_min_opportunity": 40})
    stale = MagicMock()
    stale.expire_all = AsyncMock()

    with (
        patch("app.services.calibration_service.CalibrationService", return_value=cal),
        patch("app.services.stale_signal_service.StaleSignalService", return_value=stale),
        patch.object(
            StockRefreshService,
            "build_universe",
            new=AsyncMock(return_value=(["AAA"], {"universe_size": 1})),
        ),
        patch.object(StockRefreshService, "_analyze_symbol", new=AsyncMock(return_value=None)),
    ):
        result = await svc.refresh_stocks(replace=True, limit=10)

    assert result["ok"] is True
    assert result["signals_kept"] is True
    assert result["signals_created"] == 0
    db.insert.assert_not_called()
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_options_keeps_board_when_insert_fails():
    from app.services.options_service import OptionsRefreshService

    db = MagicMock()
    db.select = AsyncMock(return_value=[])
    db.insert = AsyncMock(side_effect=HTTPException(status_code=502, detail="Database error"))
    db.delete = AsyncMock()

    svc = OptionsRefreshService(db, "user-1")
    cal = MagicMock()
    cal.get_adjustments = AsyncMock(
        return_value={
            "options_min_profit_probability": 0,
            "options_min_opportunity": 0,
            "options_budget_first": False,
        }
    )

    fake_signal = MagicMock()
    fake_signal.planned.scored.scoring_snapshot = {"profit_probability": 60}
    fake_signal.planned.scored.opportunity_score = 70
    fake_signal.planned.scored.candidate = MagicMock(premium=0.5, symbol="AAA")

    with (
        patch("app.services.calibration_service.CalibrationService", return_value=cal),
        patch.object(
            OptionsRefreshService,
            "gather_live_candidates",
            new=AsyncMock(return_value=([{"symbol": "AAA"}], {"raw_contracts": 1, "symbols_scanned": 1})),
        ),
        patch("app.services.options_service.run_options_pipeline", return_value=[fake_signal]),
        patch("app.services.options_service.select_signals_to_save", return_value=[fake_signal]),
        patch("app.services.options_service.explained_to_options_row", return_value={"user_id": "user-1"}),
        patch("app.services.options_service.is_budget_contract", return_value=False),
    ):
        result = await svc.refresh_live_options(replace=True, limit=10)

    assert result["ok"] is False
    assert result["signals_kept"] is True
    assert result["signals_created"] == 0
    assert "unchanged" in result["message"]
    db.delete.assert_not_called()
