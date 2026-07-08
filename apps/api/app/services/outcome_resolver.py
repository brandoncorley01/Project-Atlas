"""Auto-grade expired picks across sports, stocks, and options."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.providers.sports.team_stats import fetch_scores_by_sport
from app.providers.stocks.bars import fetch_daily_bars
from app.services.performance_service import PerformanceService
from app.services.sports_grading import grade_sports_pick, match_completed_game, scores_from_game
from app.services.stock_options_grading import (
    grade_options_pick,
    grade_stock_pick,
    options_ready_to_grade,
    stock_ready_to_grade,
)

logger = logging.getLogger(__name__)


async def _yahoo_spot(symbol: str) -> float:
    from app.services.options_service import _yahoo_last_price

    return await _yahoo_last_price(symbol)


class OutcomeResolverService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def resolve_pending(self, *, limit: int = 40) -> dict[str, Any]:
        """Grade expired signals that have no logged outcome yet."""
        sports = await self._resolve_sports(limit=limit)
        stocks = await self._resolve_stocks(limit=limit // 2)
        options = await self._resolve_options(limit=limit // 2)

        resolved = sports["resolved"] + stocks["resolved"] + options["resolved"]
        skipped = sports["skipped"] + stocks["skipped"] + options["skipped"]
        pending = sports["pending"] + stocks["pending"] + options["pending"]

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": pending,
            "by_module": {
                "sports": sports,
                "stock": stocks,
                "options": options,
            },
        }

    async def _graded_ids(self, module: str | None = None) -> set[str]:
        filters: dict[str, str] = {"user_id": f"eq.{self.user_id}"}
        if module:
            filters["module"] = f"eq.{module}"
        perf_rows = await self.db.select("signal_performance", filters=filters, limit=2000)
        return {
            str(r.get("signal_id"))
            for r in perf_rows
            if r.get("signal_id") and r.get("outcome") in ("win", "loss", "scratch")
        }

    async def _resolve_sports(self, *, limit: int) -> dict[str, Any]:
        graded_ids = await self._graded_ids("sports")

        signals = await self.db.select(
            "sports_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": "in.(expired,active)",
            },
            order="event_start.asc",
            limit=limit * 3,
        )

        now = datetime.now(UTC)
        candidates: list[dict[str, Any]] = []
        for sig in signals:
            sid = str(sig.get("id"))
            if sid in graded_ids:
                continue
            event_start = sig.get("event_start")
            if not event_start:
                continue
            try:
                text = str(event_start).replace("Z", "+00:00")
                start = datetime.fromisoformat(text)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                continue
            if start > now:
                continue
            candidates.append(sig)

        if not candidates:
            return {"resolved": 0, "skipped": 0, "pending": 0}

        sport_keys: set[str] = set()
        for sig in candidates[:limit]:
            snap = sig.get("scoring_snapshot") or {}
            key = snap.get("sport_key")
            if key:
                sport_keys.add(str(key))

        scores_by_sport = await fetch_scores_by_sport(sport_keys) if sport_keys else {}

        resolved = 0
        skipped = 0
        for sig in candidates[:limit]:
            snap = sig.get("scoring_snapshot") or {}
            sport_key = str(snap.get("sport_key") or "")
            games = scores_by_sport.get(sport_key) or []
            game = match_completed_game(sig, games)
            if not game:
                skipped += 1
                continue
            parsed = scores_from_game(game)
            if not parsed:
                skipped += 1
                continue
            home_score, away_score, home_team, away_team = parsed
            graded = grade_sports_pick(
                sig,
                home_score=home_score,
                away_score=away_score,
                home_team=home_team,
                away_team=away_team,
            )
            if not graded:
                skipped += 1
                continue
            outcome, return_pct = graded
            try:
                await self.performance.log_outcome(
                    module="sports",
                    signal_id=str(sig["id"]),
                    outcome=outcome,
                    return_pct=return_pct,
                    resolution_source="auto_sports",
                    signal_snapshot=sig,
                )
                await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sig['id']}"},
                    {"status": "closed"},
                )
                resolved += 1
            except Exception as exc:
                logger.warning("Auto-grade sports signal %s: %s", sig.get("id"), exc)
                skipped += 1

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": max(0, len(candidates) - resolved - skipped),
        }

    async def _resolve_stocks(self, *, limit: int) -> dict[str, Any]:
        graded_ids = await self._graded_ids("stock")
        signals = await self.db.select(
            "stock_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": "in.(expired,active)",
            },
            order="data_as_of.asc",
            limit=limit * 3,
        )

        candidates = [
            sig
            for sig in signals
            if str(sig.get("id")) not in graded_ids and stock_ready_to_grade(sig)
        ][:limit]

        if not candidates:
            return {"resolved": 0, "skipped": 0, "pending": 0}

        resolved = 0
        skipped = 0
        price_cache: dict[str, float] = {}

        async def _price(ticker: str) -> float:
            if ticker in price_cache:
                return price_cache[ticker]
            try:
                bars = await fetch_daily_bars(ticker, days=5)
                bar_list = bars.get("bars") or []
                if bar_list:
                    price_cache[ticker] = float(bar_list[-1]["close"])
                else:
                    price_cache[ticker] = await _yahoo_spot(ticker)
            except Exception:
                price_cache[ticker] = await _yahoo_spot(ticker)
            return price_cache[ticker]

        for sig in candidates:
            ticker = str(sig.get("ticker") or "").upper()
            if not ticker:
                skipped += 1
                continue
            try:
                current = await _price(ticker)
                graded = grade_stock_pick(sig, current)
                if not graded:
                    skipped += 1
                    continue
                outcome, return_pct = graded
                await self.performance.log_outcome(
                    module="stock",
                    signal_id=str(sig["id"]),
                    outcome=outcome,
                    return_pct=return_pct,
                    resolution_source="auto_stock",
                    signal_snapshot=sig,
                )
                await self.db.update(
                    "stock_signals",
                    {"id": f"eq.{sig['id']}"},
                    {"status": "closed"},
                )
                resolved += 1
            except Exception as exc:
                logger.warning("Auto-grade stock %s: %s", ticker, exc)
                skipped += 1

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": max(0, len(candidates) - resolved - skipped),
        }

    async def _resolve_options(self, *, limit: int) -> dict[str, Any]:
        graded_ids = await self._graded_ids("options")
        signals = await self.db.select(
            "options_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": "in.(expired,active,closed)",
            },
            order="expiration.asc",
            limit=limit * 3,
        )

        candidates = [
            sig
            for sig in signals
            if str(sig.get("id")) not in graded_ids and options_ready_to_grade(sig)
        ][:limit]

        if not candidates:
            return {"resolved": 0, "skipped": 0, "pending": 0}

        resolved = 0
        skipped = 0
        spot_cache: dict[str, float] = {}

        async def _spot(symbol: str) -> float:
            if symbol not in spot_cache:
                spot_cache[symbol] = await _yahoo_spot(symbol)
            return spot_cache[symbol]

        sem = asyncio.Semaphore(4)

        async def _grade_one(sig: dict[str, Any]) -> bool:
            async with sem:
                underlying = str(sig.get("underlying") or "").upper()
                if not underlying:
                    return False
                spot = await _spot(underlying)
                graded = grade_options_pick(sig, spot)
                if not graded:
                    return False
                outcome, return_pct = graded
                await self.performance.log_outcome(
                    module="options",
                    signal_id=str(sig["id"]),
                    outcome=outcome,
                    return_pct=return_pct,
                    resolution_source="auto_options",
                    signal_snapshot=sig,
                )
                await self.db.update(
                    "options_signals",
                    {"id": f"eq.{sig['id']}"},
                    {"status": "closed"},
                )
                return True

        results = await asyncio.gather(*[_grade_one(sig) for sig in candidates], return_exceptions=True)
        for r in results:
            if r is True:
                resolved += 1
            else:
                skipped += 1

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": max(0, len(candidates) - resolved - skipped),
        }
