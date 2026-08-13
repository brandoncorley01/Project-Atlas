"""Durable Odds cache: disk miss hydrates from Supabase; writes write-through."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.providers.sports import odds_api


def _sample_payload() -> dict:
    return {
        "fetched_at": "2026-08-13T12:00:00+00:00",
        "events": [
            {
                "id": "e1",
                "_sport_key": "baseball_mlb",
                "commence_time": "2026-08-14T23:00:00Z",
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {"credits_used": 8, "remote_hydrated": True},
    }


def test_read_cache_hydrates_from_remote_on_disk_miss(tmp_path: Path):
    cache_path = tmp_path / ".odds_cache.json"
    remote = _sample_payload()
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=remote) as load,
        patch("app.providers.sports.odds_cache_store.save_remote_cache") as save,
    ):
        data = odds_api._read_cache()

    assert data is not None
    assert len(data["events"]) == 1
    assert cache_path.exists()
    load.assert_called_once()
    # Hydrate writes disk only — no remote re-upsert on read.
    save.assert_not_called()
    disk = json.loads(cache_path.read_text(encoding="utf-8"))
    assert disk["events"][0]["id"] == "e1"


def test_write_cache_write_through_to_remote(tmp_path: Path):
    cache_path = tmp_path / ".odds_cache.json"
    events = _sample_payload()["events"]
    stats = {"credits_used": 6, "sports_scanned": 4}
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.save_remote_cache", return_value=True) as save,
        patch.object(odds_api, "_near_term_cache_events", return_value=(events, {})),
    ):
        odds_api._write_cache(events, stats)

    assert cache_path.exists()
    save.assert_called_once()
    payload = save.call_args.args[0]
    assert payload["events"] == events
    assert "cached" not in payload.get("stats", {})


def test_invalidate_cache_clears_remote(tmp_path: Path):
    cache_path = tmp_path / ".odds_cache.json"
    cache_path.write_text("{}", encoding="utf-8")
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.clear_remote_cache") as clear,
    ):
        odds_api._invalidate_cache()

    assert not cache_path.exists()
    clear.assert_called_once()


def test_remote_store_disabled_without_service_key():
    from app.providers.sports import odds_cache_store

    with (
        patch.object(odds_cache_store.settings, "odds_cache_remote", True),
        patch.object(odds_cache_store.settings, "supabase_url", "https://example.supabase.co"),
        patch.object(odds_cache_store.settings, "supabase_service_role_key", ""),
    ):
        assert odds_cache_store.load_remote_cache() is None
        assert odds_cache_store.save_remote_cache(_sample_payload()) is False
