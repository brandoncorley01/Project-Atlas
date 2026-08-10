"""Search bets must land on the watchlist Bets tab."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sports_user_bets_service import SportsUserBetsService


@pytest.mark.asyncio
async def test_save_bet_to_watchlist_uses_sport_event_and_kind():
    db = MagicMock()
    svc = SportsUserBetsService(db, "user-1")

    captured: dict = {}

    class FakeWatchlist:
        def __init__(self, *_a, **_k):
            pass

        async def add_item(self, *, symbol, item_type, metadata=None):
            captured["symbol"] = symbol
            captured["item_type"] = item_type
            captured["metadata"] = metadata
            return {"id": "wl-1", "symbol": symbol, "item_type": item_type, "metadata": metadata}

    import app.services.sports_user_bets_service as mod

    original = getattr(mod, "WatchlistService", None)
    # Patch via import path used inside the method.
    import app.services.watchlist_service as wl_mod

    prev = wl_mod.WatchlistService
    wl_mod.WatchlistService = FakeWatchlist  # type: ignore[misc,assignment]
    try:
        signal = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "sport": "NBA",
            "event_name": "Lakers @ Celtics",
            "bet_type": "moneyline",
            "selection": "Lakers",
            "odds_american": -110,
            "opportunity_score": 82,
            "event_start": "2099-12-01T00:00:00Z",
        }
        item = await svc._save_bet_to_watchlist(signal)
        assert item is not None
        assert captured["item_type"] == "sport_event"
        assert captured["symbol"] == signal["id"]
        assert captured["metadata"]["watchlist_kind"] == "sport_bet"
        assert captured["metadata"]["signal_id"] == signal["id"]
        assert captured["metadata"]["user_entry"] is True
        assert captured["metadata"]["selection"] == "Lakers"
    finally:
        wl_mod.WatchlistService = prev
        _ = original
