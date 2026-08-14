"""Stock swing scan, scoring, and persistence."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.stock_analyst import analyze_swing, setup_to_row
from app.db.supabase_client import SupabaseClient
from app.providers.market.universe import discover_market_symbols
from app.providers.stocks.bars import bars_to_series, fetch_daily_bars
from app.services.news_service import NewsService

logger = logging.getLogger(__name__)

SCAN_POOL_SIZE = 45
PARALLEL_FETCHES = 6
MAX_SIGNALS = 15
MIN_OPPORTUNITY = 35.0


class StockRefreshService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self._news = NewsService(db, user_id)

    async def _load_watchlist_symbols(self) -> list[str]:
        symbols: list[str] = []
        try:
            items = await self.db.select(
                "watchlist_items",
                filters={"user_id": f"eq.{self.user_id}", "item_type": "eq.ticker"},
            )
            for item in items:
                sym = str(item.get("symbol", "")).upper().strip()
                if sym:
                    symbols.append(sym)
        except Exception as exc:
            logger.warning("Watchlist load for stocks: %s", exc)
        return symbols

    async def build_universe(self) -> tuple[list[str], dict[str, Any]]:
        discovered, stats = await asyncio.to_thread(
            discover_market_symbols, max_symbols=SCAN_POOL_SIZE
        )
        watchlist = await self._load_watchlist_symbols()
        symbols: list[str] = []
        seen: set[str] = set()
        for sym in watchlist + [entry.symbol for entry in discovered]:
            sym = sym.upper()
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
        return symbols[:SCAN_POOL_SIZE], {"discovery": stats, "universe_size": len(symbols)}

    async def _analyze_symbol(self, symbol: str, *, min_opportunity: float = MIN_OPPORTUNITY) -> dict[str, Any] | None:
        payload = await fetch_daily_bars(symbol, days=120)
        bars = payload.get("bars") or []
        if len(bars) < 30:
            return None

        series = bars_to_series(bars)
        catalyst = await self._news.catalyst_for_symbol(symbol)
        setup = analyze_swing(
            symbol=symbol,
            closes=series["closes"],
            highs=series["highs"],
            lows=series["lows"],
            volumes=series["volumes"],
            catalyst=catalyst,
            chart_bars=bars,
        )
        if not setup or setup.opportunity_score < min_opportunity:
            return None
        return setup_to_row(self.user_id, setup)

    async def analyze_ticker(self, symbol: str, *, persist: bool = False) -> dict[str, Any]:
        """On-demand analysis for any ticker — chart, levels, and scoring."""
        from app.services.signal_service import SignalService

        sym = str(symbol or "").upper().strip()
        if not sym or len(sym) > 12 or not sym.replace(".", "").isalnum():
            return {"ok": False, "message": "Enter a valid ticker symbol (e.g. AAPL, NVDA)."}

        payload = await fetch_daily_bars(sym, days=120)
        bars = payload.get("bars") or []
        if len(bars) < 30:
            return {
                "ok": False,
                "message": f"Not enough price history for {sym}. Check the symbol and try again.",
            }

        series = bars_to_series(bars)
        catalyst = await self._news.catalyst_for_symbol(sym)
        setup = analyze_swing(
            symbol=sym,
            closes=series["closes"],
            highs=series["highs"],
            lows=series["lows"],
            volumes=series["volumes"],
            catalyst=catalyst,
            chart_bars=bars,
            min_setup_strength=0.0,
        )
        if not setup:
            return {"ok": False, "message": f"Could not analyze {sym}."}

        row = setup_to_row(self.user_id, setup)
        persisted = False

        if persist:
            # Insert first so a failed write cannot wipe the prior ticker row.
            try:
                saved = await self.db.insert("stock_signals", [row])
            except Exception as exc:
                logger.warning("Stock analyze insert failed for %s: %s", sym, exc)
                saved = []
            if saved:
                row = saved[0]
                persisted = True
                new_id = str(row.get("id") or "")
                try:
                    active = await self.db.select(
                        "stock_signals",
                        filters={
                            "user_id": f"eq.{self.user_id}",
                            "ticker": f"eq.{sym}",
                            "status": "eq.active",
                        },
                        select="id",
                        limit=20,
                    )
                    delete_ids = [
                        str(r.get("id"))
                        for r in active
                        if r.get("id") and str(r.get("id")) != new_id
                    ]
                    if delete_ids:
                        await self.db.delete(
                            "stock_signals",
                            {
                                "id": f"in.({','.join(delete_ids)})",
                                "user_id": f"eq.{self.user_id}",
                            },
                        )
                except Exception as exc:
                    logger.warning("Stock analyze cleanup failed for %s: %s", sym, exc)
                from app.services.signal_registry_service import SignalRegistryService

                await SignalRegistryService(self.db, self.user_id).register_batch("stock", saved)
        else:
            row["id"] = f"lookup-{sym}"

        item = SignalService(self.db, self.user_id).format_stock_item(row)
        weak = bool((row.get("scoring_snapshot") or {}).get("weak_setup"))
        message = (
            f"{sym} setup scored {setup.opportunity_score:.0f}/100 — no strong swing edge yet."
            if weak
            else f"{sym} swing analysis ready — opportunity {setup.opportunity_score:.0f}/100."
        )
        return {
            "ok": True,
            "item": item,
            "persisted": persisted,
            "weak_setup": weak,
            "message": message,
        }

    async def refresh_stocks(self, *, replace: bool = True, limit: int = MAX_SIGNALS) -> dict[str, Any]:
        from app.services.stale_signal_service import StaleSignalService

        await StaleSignalService(self.db, self.user_id).expire_all()
        from app.services.calibration_service import CalibrationService

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments()
        min_opp = float(calibration.get("stock_min_opportunity", MIN_OPPORTUNITY))
        symbols, universe_stats = await self.build_universe()
        sem = asyncio.Semaphore(PARALLEL_FETCHES)
        setups: list[dict[str, Any]] = []

        async def _run(sym: str) -> None:
            async with sem:
                try:
                    row = await self._analyze_symbol(sym, min_opportunity=min_opp)
                    if row:
                        setups.append(row)
                except Exception as exc:
                    logger.info("Stock scan skip %s: %s", sym, exc)

        await asyncio.gather(*[_run(sym) for sym in symbols])

        setups.sort(key=lambda r: float(r["opportunity_score"]), reverse=True)
        setups = setups[:limit]

        if not setups:
            return {
                "signals_created": 0,
                "signals_kept": True,
                "ok": True,
                "symbols_scanned": len(symbols),
                "stats": universe_stats,
                "top_opportunity": None,
                "calibration": calibration,
                "message": "No swing setups met the minimum score threshold — your current picks are unchanged.",
            }

        # Insert BEFORE delete so a failed save cannot wipe the board.
        saved: list[dict[str, Any]] = []
        insert_error: str | None = None
        try:
            inserted = await self.db.insert("stock_signals", setups)
            if inserted:
                saved = inserted
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            insert_error = str(detail)[:180]
            logger.warning("Stock insert failed (%s rows): %s", len(setups), exc)

        if not saved:
            return {
                "signals_created": 0,
                "signals_kept": True,
                "ok": False,
                "symbols_scanned": len(symbols),
                "stats": universe_stats,
                "top_opportunity": float(setups[0]["opportunity_score"]),
                "calibration": calibration,
                "message": (
                    "Stocks scan scored picks but failed to save them — your board was left unchanged. "
                    f"{insert_error or 'Database write failed.'}"
                ),
            }

        if replace and saved:
            try:
                from app.services.outcome_resolver import OutcomeResolverService

                await OutcomeResolverService(self.db, self.user_id).resolve_pending(
                    limit=40,
                    module="stock",
                )
            except Exception as exc:
                logger.warning("Pre-replace stock auto-grade skipped: %s", exc)

            saved_ids = {str(r.get("id")) for r in saved if r.get("id")}
            active = await self.db.select(
                "stock_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                select="id",
                limit=400,
            )
            delete_ids = [
                str(row.get("id"))
                for row in active
                if row.get("id") and str(row.get("id")) not in saved_ids
            ]
            for start in range(0, len(delete_ids), 40):
                chunk = delete_ids[start : start + 40]
                try:
                    await self.db.delete(
                        "stock_signals",
                        {"id": f"in.({','.join(chunk)})", "user_id": f"eq.{self.user_id}"},
                    )
                except Exception as exc:
                    logger.warning("Failed to clear old stock chunk: %s", exc)

        if saved:
            from app.services.alert_service import AlertService
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("stock", saved)
            await AlertService(self.db, self.user_id).notify_high_score_signals(
                "stock",
                saved,
                title_fn=lambda s: f"Stock swing · {s.get('ticker')} ({float(s.get('opportunity_score') or 0):.0f}/100)",
            )

        return {
            "signals_created": len(saved),
            "ok": True,
            "symbols_scanned": len(symbols),
            "stats": universe_stats,
            "top_opportunity": float(setups[0]["opportunity_score"]) if setups else None,
            "calibration": calibration,
            "message": None,
        }
