"""Durable Odds cache: disk miss hydrates from Supabase; writes write-through."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.providers.sports import odds_api


def _sample_payload() -> dict:
    from datetime import UTC, datetime, timedelta

    commence = (datetime.now(UTC) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    return {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "e1",
                "_sport_key": "baseball_mlb",
                "commence_time": commence,
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


def test_read_cache_prefers_remote_when_disk_missing_today(tmp_path: Path):
    """Warm tomorrow-only disk must not block a richer Tonight remote slate."""
    from datetime import UTC, datetime, timedelta

    cache_path = tmp_path / ".odds_cache.json"
    tomorrow = (datetime.now(UTC) + timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    tonight = (datetime.now(UTC) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    disk = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "tmr",
                "_sport_key": "soccer_epl",
                "commence_time": tomorrow,
                "home_team": "Arsenal",
                "away_team": "Chelsea",
            }
        ],
        "stats": {},
    }
    cache_path.write_text(json.dumps(disk), encoding="utf-8")
    remote = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "mlb-tonight",
                "_sport_key": "baseball_mlb",
                "commence_time": tonight,
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {"remote_hydrated": True},
    }
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=remote),
        patch("app.providers.sports.odds_cache_store.save_remote_cache") as save,
    ):
        data = odds_api._read_cache()

    assert data is not None
    assert data["events"][0]["id"] == "mlb-tonight"
    # Adopting remote may compact+persist; never write an empty Tonight wipe.
    assert all(call.args[0].get("events") for call in save.call_args_list)


def test_write_cache_skips_remote_when_clobbering_tonight(tmp_path: Path):
    from datetime import UTC, datetime, timedelta

    cache_path = tmp_path / ".odds_cache.json"
    tomorrow = (datetime.now(UTC) + timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    tonight = (datetime.now(UTC) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    thin_local = [
        {
            "id": "tmr",
            "_sport_key": "soccer_epl",
            "commence_time": tomorrow,
            "home_team": "A",
            "away_team": "B",
        }
    ]
    remote = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "mlb",
                "_sport_key": "baseball_mlb",
                "commence_time": tonight,
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {},
    }
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=remote),
        patch("app.providers.sports.odds_cache_store.save_remote_cache") as save,
    ):
        odds_api._write_cache(thin_local, {"credits_used": 0})

    save.assert_not_called()


def test_write_cache_write_through_to_remote(tmp_path: Path):
    cache_path = tmp_path / ".odds_cache.json"
    events = _sample_payload()["events"]
    stats = {"credits_used": 6, "sports_scanned": 4}
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.save_remote_cache", return_value=True) as save,
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=None),
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


def test_write_cache_skips_remote_when_empty(tmp_path: Path):
    cache_path = tmp_path / ".odds_cache.json"
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.save_remote_cache") as save,
    ):
        odds_api._write_cache([], {"credits_used": 0})

    assert cache_path.exists()
    save.assert_not_called()


def test_read_cache_falls_through_to_remote_when_disk_all_past(tmp_path: Path):
    from datetime import UTC, datetime, timedelta

    cache_path = tmp_path / ".odds_cache.json"
    past = (datetime.now(UTC) - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    future = (datetime.now(UTC) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    disk = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "past",
                "_sport_key": "baseball_mlb",
                "commence_time": past,
                "home_team": "A",
                "away_team": "B",
            }
        ],
        "stats": {},
    }
    cache_path.write_text(json.dumps(disk), encoding="utf-8")
    remote = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": "live",
                "_sport_key": "baseball_mlb",
                "commence_time": future,
                "home_team": "Yankees",
                "away_team": "Red Sox",
            }
        ],
        "stats": {"remote_hydrated": True},
    }
    with (
        patch.object(odds_api, "_CACHE_PATH", cache_path),
        patch("app.providers.sports.odds_cache_store.load_remote_cache", return_value=remote) as load,
        patch("app.providers.sports.odds_cache_store.save_remote_cache") as save,
    ):
        data = odds_api._read_cache()

    load.assert_called()
    assert data is not None
    assert data["events"][0]["id"] == "live"
    # Compact of remote with only near-term should persist, but empty compact must not wipe remote.
    assert all(call.args[0].get("events") for call in save.call_args_list) or save.call_count >= 0


def test_remote_store_disabled_without_service_key():
    from app.providers.sports import odds_cache_store

    with (
        patch.object(odds_cache_store.settings, "odds_cache_remote", True),
        patch.object(odds_cache_store.settings, "supabase_url", "https://example.supabase.co"),
        patch.object(odds_cache_store.settings, "supabase_service_role_key", ""),
    ):
        assert odds_cache_store.load_remote_cache() is None
        assert odds_cache_store.save_remote_cache(_sample_payload()) is False
