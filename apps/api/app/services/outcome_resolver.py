"""Auto-grade expired picks across sports, stocks, options, and parlays."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.db.supabase_client import SupabaseClient
from app.providers.sports.team_stats import fetch_scores_by_sport
from app.providers.stocks.bars import fetch_daily_bars
from app.services.performance_service import PerformanceService
from app.services.sports_grading import (
    grade_parlay_from_legs,
    grade_sports_pick,
    match_completed_game,
    scores_from_game,
)
from app.services.stock_options_grading import (
    grade_options_pick,
    grade_stock_pick,
    options_ready_to_grade,
    stock_ready_to_grade,
)

logger = logging.getLogger(__name__)

GRADEABLE_SPORTS_BET_TYPES = frozenset({"moneyline", "spread", "total", "ml", "h2h"})
# Props and exotic markets cannot be auto-scored from final team scores alone.
UNGRADEABLE_SPORTS_BET_TYPES = frozenset(
    {
        "player_prop",
        "prop",
        "futures",
        "outright",
        "fight_prop",
        "period",
        "quarter",
        "half",
    }
)


async def _yahoo_spot(symbol: str) -> float:
    from app.services.options_service import _yahoo_last_price

    return await _yahoo_last_price(symbol)


def _hours_since(iso_value: Any) -> float | None:
    if not iso_value:
        return None
    try:
        text = str(iso_value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def sports_bet_type(signal: dict[str, Any]) -> str:
    snap = signal.get("scoring_snapshot") if isinstance(signal.get("scoring_snapshot"), dict) else {}
    pick = snap.get("pick") if isinstance(snap.get("pick"), dict) else {}
    raw = str(
        signal.get("bet_type")
        or snap.get("bet_type")
        or pick.get("bet_type")
        or ""
    ).lower().strip()
    if raw in {"ml", "h2h"}:
        return "moneyline"
    return raw


def is_auto_gradeable_sports(signal: dict[str, Any]) -> bool:
    bet = sports_bet_type(signal)
    if bet in UNGRADEABLE_SPORTS_BET_TYPES:
        return False
    if bet in GRADEABLE_SPORTS_BET_TYPES:
        return True
    # Unknown but looks like a side/total line — still try.
    snap = signal.get("scoring_snapshot") if isinstance(signal.get("scoring_snapshot"), dict) else {}
    return bool(snap.get("sport_key") or signal.get("selection") or snap.get("selection"))


def signal_from_performance_row(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a gradeable signal dict from a durable signal_performance row.

    Rescans hard-delete live board rows; grading must survive on the snapshot alone.
    """
    snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
    sid = str(row.get("signal_id") or "")
    sig: dict[str, Any] = {
        "id": sid,
        "scoring_snapshot": snap,
        "status": snap.get("status") or "expired",
        "data_as_of": snap.get("data_as_of") or row.get("logged_at"),
    }
    for key in (
        "sport",
        "bet_type",
        "selection",
        "odds_american",
        "event_name",
        "event_start",
        "expected_value",
        "underlying",
        "option_type",
        "strike",
        "expiration",
        "premium",
        "ticker",
        "symbol",
        "recommendation",
        "entry_range",
        "stop_loss",
        "profit_targets",
        "current_price",
        "opportunity_score",
        "confidence_score",
    ):
        if snap.get(key) is not None:
            sig[key] = snap[key]
    if not sig.get("ticker") and snap.get("symbol"):
        sig["ticker"] = snap["symbol"]
    if not sig.get("event_start") and snap.get("event_start"):
        sig["event_start"] = snap["event_start"]
    return sig


class OutcomeResolverService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self.performance = PerformanceService(db, user_id)

    async def resolve_pending(
        self,
        *,
        limit: int = 120,
        module: str | None = None,
        passes: int = 1,
    ) -> dict[str, Any]:
        """Grade expired signals that have no logged outcome yet.

        ``passes`` > 1 walks the backlog in chunks so ungradable props cannot
        permanently block moneyline/spread/total grading (954+ open piles).
        """
        passes = max(1, min(int(passes or 1), 12))
        limit = max(20, min(int(limit or 120), 400))

        totals = {
            "resolved": 0,
            "skipped": 0,
            "pending": 0,
            "scratched_stale": 0,
            "module": module,
            "passes": 0,
            "by_module": {},
        }

        for pass_i in range(passes):
            pass_result = await self._resolve_pending_once(limit=limit, module=module)
            totals["passes"] = pass_i + 1
            totals["resolved"] += pass_result["resolved"]
            totals["skipped"] += pass_result["skipped"]
            totals["pending"] = pass_result["pending"]
            totals["scratched_stale"] += pass_result["scratched_stale"]
            for mod, stats in (pass_result.get("by_module") or {}).items():
                bucket = totals["by_module"].setdefault(
                    mod, {"resolved": 0, "skipped": 0, "pending": 0, "scratched_stale": 0}
                )
                for key in ("resolved", "skipped", "scratched_stale"):
                    bucket[key] += int(stats.get(key) or 0)
                bucket["pending"] = int(stats.get("pending") or 0)

            progressed = int(pass_result["resolved"]) + int(pass_result["scratched_stale"])
            if progressed == 0:
                break

        return totals

    async def _resolve_pending_once(self, *, limit: int, module: str | None) -> dict[str, Any]:
        empty = {"resolved": 0, "skipped": 0, "pending": 0, "scratched_stale": 0}
        by_module: dict[str, dict[str, Any]] = {}

        if module in (None, "sports"):
            sports = await self._resolve_sports(limit=limit if module == "sports" else limit)
            stale = await self._prune_stale_sports_pending(limit=max(200, limit * 2))
            sports = {**sports, "scratched_stale": stale}
            by_module["sports"] = sports
        else:
            sports = empty

        if module in (None, "stock"):
            stock_limit = limit if module == "stock" else max(40, limit // 2)
            stocks = await self._resolve_stocks(limit=stock_limit)
            by_module["stock"] = stocks
        else:
            stocks = empty

        if module in (None, "options"):
            options_limit = limit if module == "options" else max(40, limit // 2)
            options = await self._resolve_options(limit=options_limit)
            by_module["options"] = options
        else:
            options = empty

        if module in (None, "parlay"):
            parlay_limit = limit if module == "parlay" else max(12, limit // 3)
            parlays = await self._resolve_parlays(limit=parlay_limit)
            by_module["parlay"] = parlays
        else:
            parlays = empty

        resolved = sports["resolved"] + stocks["resolved"] + options["resolved"] + parlays["resolved"]
        skipped = sports["skipped"] + stocks["skipped"] + options["skipped"] + parlays["skipped"]
        pending = sports["pending"] + stocks["pending"] + options["pending"] + parlays["pending"]
        scratched = int(sports.get("scratched_stale") or 0)

        return {
            "resolved": resolved,
            "skipped": skipped,
            "pending": max(0, pending),
            "scratched_stale": scratched,
            "module": module,
            "by_module": by_module,
        }

    async def _prune_stale_sports_pending(self, *, limit: int = 200) -> int:
        """Clear open sports pending after the event is long over and ungradable.

        Important: fetch a large window and scratch every eligible row in it.
        Previously the oldest ungradable props consumed the limit and blocked
        finished moneylines from ever leaving "open".
        """
        rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "module": "eq.sports",
                "outcome": "eq.pending",
            },
            order="logged_at.asc",
            limit=max(limit, 250),
        )
        if not rows:
            return 0

        scratched = 0
        # Prefer clearing known-finished / ungradable markets first.
        ranked = sorted(
            rows,
            key=lambda r: (
                0 if _hours_since((r.get("scoring_snapshot") or {}).get("event_start")) is not None else 1,
                0 if not is_auto_gradeable_sports(signal_from_performance_row(r)) else 1,
                str(r.get("logged_at") or ""),
            ),
        )

        for row in ranked:
            if scratched >= limit:
                break
            sid = str(row.get("signal_id") or "")
            if not sid:
                continue
            snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
            event_start = snap.get("event_start")
            status = None
            try:
                sig_rows = await self.db.select(
                    "sports_signals",
                    filters={"id": f"eq.{sid}", "user_id": f"eq.{self.user_id}"},
                    limit=1,
                )
                if sig_rows:
                    event_start = event_start or sig_rows[0].get("event_start")
                    status = str(sig_rows[0].get("status") or "")
                    nested = sig_rows[0].get("scoring_snapshot")
                    if isinstance(nested, dict) and not snap.get("event_start"):
                        event_start = event_start or nested.get("event_start")
            except Exception as exc:
                logger.debug("Stale prune signal lookup %s: %s", sid[:8], exc)

            hours_past = _hours_since(event_start)
            age_h = _hours_since(row.get("logged_at"))
            bet = sports_bet_type(signal_from_performance_row(row))
            ungradable = bet in UNGRADEABLE_SPORTS_BET_TYPES or (
                bool(snap.get("is_player_prop") or snap.get("is_futures") or snap.get("is_fight_prop"))
            )

            # Props / futures: leave open briefly, then scratch — they cannot auto-score.
            if ungradable:
                prop_stale_h = 12.0 if hours_past is not None else 48.0
                marker = hours_past if hours_past is not None else age_h
                if marker is None or marker < prop_stale_h:
                    continue
                hours_past = marker
            else:
                # Gradeable markets: wait for finals; if still open long after tip-off, scratch.
                stale_after_h = 18.0
                if hours_past is None:
                    if status in {"expired", "closed"} and age_h is not None and age_h >= 48:
                        hours_past = age_h
                    elif age_h is not None and age_h >= 72:
                        # Snapshot-only leftovers with no event_start — clear open pile.
                        hours_past = age_h
                    else:
                        continue
                if hours_past < stale_after_h:
                    continue

            try:
                await self.performance.log_outcome(
                    module="sports",
                    signal_id=sid,
                    outcome="scratch",
                    return_pct=0.0,
                    resolution_source="auto_sports_stale",
                    signal_snapshot={
                        **snap,
                        "stale_cleared": True,
                        "stale_hours_past": round(float(hours_past), 1),
                        "graded_by": "auto_sports_stale",
                        "ungradeable_market": ungradable,
                    },
                )
                if status in {"active", "expired"}:
                    try:
                        await self.db.update(
                            "sports_signals",
                            {"id": f"eq.{sid}"},
                            {"status": "closed"},
                        )
                    except Exception:
                        pass
                scratched += 1
            except Exception as exc:
                logger.warning("Stale sports prune %s: %s", sid[:8], exc)

        if scratched:
            logger.info("Pruned %s stale pending sports picks from open count", scratched)
        return scratched

    async def _pending_performance(self, module: str, *, limit: int) -> list[dict[str, Any]]:
        return await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "module": f"eq.{module}",
                "outcome": "eq.pending",
            },
            order="logged_at.asc",
            limit=limit,
        )

    async def _load_live_signal(self, module: str, signal_id: str) -> dict[str, Any] | None:
        table = {
            "sports": "sports_signals",
            "stock": "stock_signals",
            "options": "options_signals",
            "parlay": "parlays",
        }.get(module)
        if not table or not signal_id:
            return None
        try:
            rows = await self.db.select(
                table,
                filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
                limit=1,
            )
            return rows[0] if rows else None
        except Exception as exc:
            logger.debug("Live signal lookup %s %s: %s", module, signal_id[:8], exc)
            return None

    async def _candidate_signals(self, module: str, *, limit: int) -> list[dict[str, Any]]:
        """Prefer durable pending performance rows; enrich with live signal when present."""
        # Pull a wider window so we can prioritize gradeable sports over props.
        pending = await self._pending_performance(module, limit=max(limit * 4, 200))
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in pending:
            sid = PerformanceService._normalize_signal_id(str(row.get("signal_id") or ""))
            if not sid or sid in seen:
                continue
            seen.add(sid)
            live = await self._load_live_signal(module, sid)
            if live:
                snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
                live_snap = live.get("scoring_snapshot") if isinstance(live.get("scoring_snapshot"), dict) else {}
                merged_snap = {**snap, **live_snap}
                sig = {**live, "scoring_snapshot": merged_snap, "id": live.get("id") or sid}
            else:
                sig = signal_from_performance_row(row)
            candidates.append(sig)

        if len(candidates) < limit:
            table = {
                "sports": "sports_signals",
                "stock": "stock_signals",
                "options": "options_signals",
            }.get(module)
            if table:
                try:
                    order = {
                        "sports": "event_start.asc",
                        "stock": "data_as_of.asc",
                        "options": "expiration.asc",
                    }[module]
                    live_rows = await self.db.select(
                        table,
                        filters={
                            "user_id": f"eq.{self.user_id}",
                            "status": "in.(expired,active,closed)",
                        },
                        order=order,
                        limit=limit,
                    )
                    for sig in live_rows:
                        sid = PerformanceService._normalize_signal_id(str(sig.get("id") or ""))
                        if not sid or sid in seen:
                            continue
                        seen.add(sid)
                        candidates.append(sig)
                except Exception as exc:
                    logger.debug("Live candidate load %s: %s", module, exc)

        if module == "sports":
            # Grade moneyline/spread/total first — props previously filled the whole batch.
            candidates.sort(
                key=lambda s: (
                    0 if is_auto_gradeable_sports(s) else 1,
                    str(s.get("event_start") or ""),
                )
            )

        return candidates[: max(limit * 2, limit)]

    async def _resolve_sports(self, *, limit: int) -> dict[str, Any]:
        now = datetime.now(UTC)
        raw = await self._candidate_signals("sports", limit=limit)
        candidates: list[dict[str, Any]] = []
        for sig in raw:
            if not is_auto_gradeable_sports(sig):
                continue
            snap = sig.get("scoring_snapshot") or {}
            event_start = sig.get("event_start") or snap.get("event_start")
            if event_start:
                try:
                    text = str(event_start).replace("Z", "+00:00")
                    start = datetime.fromisoformat(text)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=UTC)
                except (TypeError, ValueError):
                    continue
                if start > now:
                    continue
            else:
                has_match_key = bool(
                    snap.get("sport_key")
                    and (
                        snap.get("event_id")
                        or (snap.get("home_team") and snap.get("away_team"))
                        or sig.get("event_name")
                        or snap.get("event_name")
                    )
                )
                if not has_match_key:
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

        scores_by_sport = (
            await fetch_scores_by_sport(sport_keys, force_refresh=True) if sport_keys else {}
        )
        # Flat list for snapshots missing sport_key — still try team/event match.
        all_games: list[dict[str, Any]] = []
        for g_list in scores_by_sport.values():
            all_games.extend(g_list)

        resolved = 0
        skipped = 0
        for sig in candidates[:limit]:
            snap = sig.get("scoring_snapshot") or {}
            sport_key = str(snap.get("sport_key") or "")
            games = list(scores_by_sport.get(sport_key) or [])
            if not games:
                games = all_games
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
                try:
                    await self.db.update(
                        "sports_signals",
                        {"id": f"eq.{sig['id']}"},
                        {"status": "closed"},
                    )
                except Exception:
                    pass
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
        raw = await self._candidate_signals("stock", limit=limit)
        candidates = [sig for sig in raw if stock_ready_to_grade(sig)][:limit]

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
            ticker = str(sig.get("ticker") or sig.get("symbol") or "").upper()
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
                try:
                    await self.db.update(
                        "stock_signals",
                        {"id": f"eq.{sig['id']}"},
                        {"status": "closed"},
                    )
                except Exception:
                    pass
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
        raw = await self._candidate_signals("options", limit=limit)
        candidates = [sig for sig in raw if options_ready_to_grade(sig)][:limit]

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
                try:
                    await self.db.update(
                        "options_signals",
                        {"id": f"eq.{sig['id']}"},
                        {"status": "closed"},
                    )
                except Exception:
                    pass
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

    async def _resolve_parlays(self, *, limit: int) -> dict[str, Any]:
        """Grade parlays once every leg's event has a final score."""
        pending_perf = await self._pending_performance("parlay", limit=limit * 3)
        parlays = await self.db.select(
            "parlays",
            filters={"user_id": f"eq.{self.user_id}"},
            order="created_at.asc",
            limit=limit * 3,
        )

        by_id: dict[str, dict[str, Any]] = {}
        for row in pending_perf:
            sid = PerformanceService._normalize_signal_id(str(row.get("signal_id") or ""))
            if sid:
                by_id[sid] = signal_from_performance_row(row)
        for row in parlays:
            sid = PerformanceService._normalize_signal_id(str(row.get("id") or ""))
            if sid:
                by_id[sid] = row

        candidates = list(by_id.values())[:limit]
        if not candidates:
            return {"resolved": 0, "skipped": 0, "pending": 0}

        for row in candidates:
            sid = str(row.get("id") or "")
            if not sid:
                continue
            existing = await self.performance.get_outcome(module="parlay", signal_id=sid)
            if not existing:
                try:
                    await self.performance.log_outcome(
                        module="parlay",
                        signal_id=sid,
                        outcome="pending",
                        resolution_source="auto_scan",
                        signal_snapshot=row,
                    )
                except Exception as exc:
                    logger.warning("Register parlay %s for grading: %s", sid[:8], exc)

        resolved = 0
        skipped = 0
        pending = 0

        for row in candidates:
            parlay_id = str(row.get("id") or "")
            if not parlay_id:
                skipped += 1
                continue
            try:
                result = await self._grade_one_parlay(row)
            except Exception as exc:
                logger.warning("Auto-grade parlay %s: %s", parlay_id[:8], exc)
                skipped += 1
                continue
            if result is None:
                pending += 1
                continue
            outcome, return_pct, leg_outcomes = result
            try:
                snap = dict(row.get("scoring_snapshot") or {})
                snap["leg_outcomes"] = leg_outcomes
                snap["graded_by"] = "auto_parlay"
                await self.performance.log_outcome(
                    module="parlay",
                    signal_id=parlay_id,
                    outcome=outcome,
                    return_pct=return_pct,
                    resolution_source="auto_parlay",
                    signal_snapshot={**row, "scoring_snapshot": snap, "legs": leg_outcomes},
                )
                if str(row.get("status") or "") == "active":
                    try:
                        await self.db.update(
                            "parlays",
                            {"id": f"eq.{parlay_id}"},
                            {"status": "closed"},
                        )
                    except Exception:
                        pass
                resolved += 1
            except Exception as exc:
                logger.warning("Log parlay grade %s: %s", parlay_id[:8], exc)
                skipped += 1

        return {"resolved": resolved, "skipped": skipped, "pending": pending}

    async def _grade_one_parlay(
        self, parlay: dict[str, Any]
    ) -> tuple[str, float, list[dict[str, Any]]] | None:
        parlay_id = str(parlay["id"])
        legs = await self.db.select(
            "parlay_legs",
            filters={
                "parlay_id": f"eq.{parlay_id}",
                "user_id": f"eq.{self.user_id}",
            },
            order="leg_order.asc",
            limit=12,
        )
        # Snapshot-only parlays may store legs in scoring_snapshot after live rows vanish.
        if not legs:
            snap = parlay.get("scoring_snapshot") if isinstance(parlay.get("scoring_snapshot"), dict) else {}
            snap_legs = snap.get("leg_outcomes") or snap.get("legs") or parlay.get("legs")
            if isinstance(snap_legs, list) and snap_legs:
                # Already graded legs in snapshot — reconstruct outcome codes if present.
                codes = [str(leg.get("outcome") or "") for leg in snap_legs]
                if codes and all(c in ("win", "loss", "scratch") for c in codes):
                    odds = parlay.get("combined_odds_american") or snap.get("combined_odds_american")
                    try:
                        odds_int = int(odds) if odds is not None else None
                    except (TypeError, ValueError):
                        odds_int = None
                    ticket = grade_parlay_from_legs(codes, combined_odds_american=odds_int)
                    if ticket:
                        return ticket[0], ticket[1], list(snap_legs)
            return None

        signal_ids = [
            str(leg.get("sports_signal_id"))
            for leg in legs
            if leg.get("sports_signal_id")
        ]
        signal_map: dict[str, dict[str, Any]] = {}
        if signal_ids:
            try:
                rows = await self.db.select(
                    "sports_signals",
                    filters={
                        "user_id": f"eq.{self.user_id}",
                        "id": f"in.({','.join(signal_ids)})",
                    },
                    limit=len(signal_ids),
                )
                signal_map = {
                    PerformanceService._normalize_signal_id(str(r["id"])): r for r in rows
                }
            except Exception as exc:
                logger.warning("Load parlay leg signals: %s", exc)

        # Fall back to performance snapshots for deleted leg signals.
        missing = [sid for sid in signal_ids if PerformanceService._normalize_signal_id(sid) not in signal_map]
        for sid in missing:
            try:
                perf = await self.performance.get_outcome(module="sports", signal_id=sid)
                if perf and isinstance(perf.get("scoring_snapshot"), dict):
                    signal_map[PerformanceService._normalize_signal_id(sid)] = signal_from_performance_row(
                        {
                            "signal_id": sid,
                            "scoring_snapshot": perf["scoring_snapshot"],
                            "logged_at": perf.get("logged_at"),
                        }
                    )
            except Exception:
                pass

        now = datetime.now(UTC)
        sport_keys: set[str] = set()
        leg_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

        for leg in legs:
            sid = leg.get("sports_signal_id")
            sig = (
                signal_map.get(PerformanceService._normalize_signal_id(str(sid)))
                if sid
                else None
            )
            if not sig:
                sig = {
                    "id": sid,
                    "bet_type": leg.get("bet_type"),
                    "selection": leg.get("selection"),
                    "odds_american": leg.get("odds_american"),
                    "event_name": leg.get("event_name"),
                    "sport": leg.get("sport"),
                    "event_start": None,
                    "scoring_snapshot": {"sport_key": None},
                }
            event_start = sig.get("event_start") or leg.get("event_start")
            if event_start:
                try:
                    text = str(event_start).replace("Z", "+00:00")
                    start = datetime.fromisoformat(text)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=UTC)
                    if start > now:
                        return None
                except (TypeError, ValueError):
                    pass
            snap = sig.get("scoring_snapshot") or {}
            key = snap.get("sport_key") or leg.get("sport")
            if key:
                sport_keys.add(str(key))
            leg_pairs.append((leg, sig))

        scores_by_sport = await fetch_scores_by_sport(sport_keys) if sport_keys else {}

        outcome_codes: list[str] = []
        leg_details: list[dict[str, Any]] = []
        for order, (leg, sig) in enumerate(leg_pairs, start=1):
            snap = sig.get("scoring_snapshot") or {}
            sport_key = str(snap.get("sport_key") or "")
            games = list(scores_by_sport.get(sport_key) or [])
            if not games and scores_by_sport:
                for g_list in scores_by_sport.values():
                    games.extend(g_list)
            game = match_completed_game(sig, games)
            if not game:
                return None
            parsed = scores_from_game(game)
            if not parsed:
                return None
            home_score, away_score, home_team, away_team = parsed
            graded = grade_sports_pick(
                sig,
                home_score=home_score,
                away_score=away_score,
                home_team=home_team,
                away_team=away_team,
            )
            if not graded:
                return None
            leg_outcome = graded[0]
            outcome_codes.append(leg_outcome)
            try:
                odds_american = int(leg.get("odds_american") if leg.get("odds_american") is not None else sig.get("odds_american") or 0)
            except (TypeError, ValueError):
                odds_american = 0
            leg_details.append(
                {
                    "leg_order": int(leg.get("leg_order") or order),
                    "sport": leg.get("sport") or sig.get("sport"),
                    "event_name": leg.get("event_name") or sig.get("event_name"),
                    "bet_type": leg.get("bet_type") or sig.get("bet_type"),
                    "selection": leg.get("selection") or sig.get("selection"),
                    "odds_american": odds_american,
                    "outcome": leg_outcome,
                    "sports_signal_id": leg.get("sports_signal_id") or sig.get("id"),
                }
            )

        odds = parlay.get("combined_odds_american")
        try:
            odds_int = int(odds) if odds is not None else None
        except (TypeError, ValueError):
            odds_int = None
        ticket = grade_parlay_from_legs(outcome_codes, combined_odds_american=odds_int)
        if not ticket:
            return None
        return ticket[0], ticket[1], leg_details
