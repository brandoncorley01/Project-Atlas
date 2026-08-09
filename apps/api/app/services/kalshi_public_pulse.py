"""Attach Kalshi public-probability pulses to sports signals (card indicator)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app import config
from app.providers.sports.kalshi import (
    fetch_series_events,
    public_pulse_for_matchup,
    series_for_sport,
)

logger = logging.getLogger(__name__)


def _participants(row: dict[str, Any]) -> tuple[str, str]:
    snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
    home = str(snap.get("home_team") or "").strip()
    away = str(snap.get("away_team") or "").strip()
    if home and away:
        return home, away

    event = str(row.get("event_name") or "")
    if " @ " in event:
        away_part, home_part = event.split(" @ ", 1)
        return home_part.strip(), away_part.strip()
    if re.search(r"\s+vs\.?\s+", event, flags=re.I):
        parts = re.split(r"\s+vs\.?\s+", event, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return home, away


def _sport_key(row: dict[str, Any]) -> str | None:
    snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
    lm = row.get("line_movement") if isinstance(row.get("line_movement"), dict) else {}
    key = snap.get("sport_key") or lm.get("sport_key")
    return str(key) if key else None


async def enrich_sports_rows_with_kalshi(
    rows: list[dict[str, Any]],
    *,
    max_rows: int = 24,
    include_history: bool = True,
    timeout_sec: float = 3.5,
) -> list[dict[str, Any]]:
    """Best-effort: attach `public_market` onto formatted sports items."""
    if not config.settings.atlas_kalshi_public_pulse_enabled or not rows:
        return rows

    async def _one(row: dict[str, Any]) -> None:
        if row.get("public_market"):
            return
        snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
        cached = snap.get("public_market")
        if isinstance(cached, dict) and cached.get("source") == "kalshi":
            row["public_market"] = cached
            return
        home, away = _participants(row)
        if not home or not away:
            return
        try:
            pulse = await public_pulse_for_matchup(
                home_team=home,
                away_team=away,
                sport_key=_sport_key(row),
                sport=str(row.get("sport") or ""),
                selection=str(row.get("selection") or ""),
                include_history=include_history,
            )
        except Exception as exc:
            logger.info("Kalshi pulse enrich skipped: %s", exc)
            return
        if pulse:
            row["public_market"] = pulse

    targets = rows[: max(0, max_rows)]
    # Warm series caches once so concurrent matchups don't stampede Kalshi.
    series_needed = {
        series_for_sport(sport_key=_sport_key(r), sport=str(r.get("sport") or ""))
        for r in targets
    }
    series_needed.discard(None)
    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(fetch_series_events(s) for s in series_needed if s),
                return_exceptions=True,
            ),
            timeout=min(timeout_sec, 2.5),
        )
    except TimeoutError:
        logger.info("Kalshi series warm-up timed out")
    except Exception as exc:
        logger.info("Kalshi series warm-up failed: %s", exc)

    try:
        await asyncio.wait_for(
            asyncio.gather(*(_one(r) for r in targets), return_exceptions=True),
            timeout=timeout_sec,
        )
    except TimeoutError:
        logger.info("Kalshi pulse enrich timed out after %.1fs", timeout_sec)
    except Exception as exc:
        logger.info("Kalshi pulse enrich failed: %s", exc)
    return rows


async def enrich_setup_snapshots_with_kalshi(setups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """During scan/refresh — persist pulse on scoring_snapshot when matched."""
    if not config.settings.atlas_kalshi_public_pulse_enabled or not setups:
        return setups

    async def _one(row: dict[str, Any]) -> None:
        snap = row.setdefault("scoring_snapshot", {})
        if isinstance(snap.get("public_market"), dict):
            return
        home = str(snap.get("home_team") or "").strip()
        away = str(snap.get("away_team") or "").strip()
        if not home or not away:
            home, away = _participants(row)
        if not home or not away:
            return
        pulse = await public_pulse_for_matchup(
            home_team=home,
            away_team=away,
            sport_key=str(snap.get("sport_key") or "") or None,
            sport=str(row.get("sport") or ""),
            selection=str(row.get("selection") or ""),
            include_history=True,
        )
        if pulse:
            snap["public_market"] = pulse
            row["public_market"] = pulse

    try:
        await asyncio.wait_for(
            asyncio.gather(*(_one(r) for r in setups[:40]), return_exceptions=True),
            timeout=6.0,
        )
    except TimeoutError:
        logger.info("Kalshi snapshot enrich timed out")
    except Exception as exc:
        logger.info("Kalshi snapshot enrich failed: %s", exc)
    return setups
