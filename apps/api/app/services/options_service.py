import asyncio
import logging

from app.config import settings
from app.db.supabase_client import SupabaseClient, explained_to_options_row
from app.engine.pipeline import run_options_pipeline
from app.providers.market.universe import (
    DiscoveredSymbol,
    discover_market_symbols,
    pre_score_symbol,
)
from app.agents.scout import contract_cost, is_budget_contract
from app.providers.options.yahoo import fetch_options_candidates
from app.providers.stocks.finnhub import FinnhubClient, FinnhubError

logger = logging.getLogger(__name__)

DISCOVERY_POOL_SIZE = 55
DEEP_DIVE_SYMBOL_LIMIT = 28
MAX_SIGNALS_OUTPUT = 15
MAX_SIGNALS_STORED = 35
MAX_BUDGET_SIGNALS = 10
MAX_PER_SYMBOL = 3
FINNHUB_CONTEXT_LIMIT = 28
PARALLEL_SYMBOL_FETCHES = 6


def contract_identity_key(candidate: object) -> str:
    """Stable contract identity — normalize strike so 18 and 18.0 cannot both save."""
    symbol = str(getattr(candidate, "symbol", "") or "").upper()
    option_type = str(getattr(candidate, "option_type", "") or "").lower()
    try:
        strike = f"{float(getattr(candidate, 'strike', 0) or 0):.2f}"
    except (TypeError, ValueError):
        strike = "0.00"
    expiration = getattr(candidate, "expiration", None)
    return f"{symbol}:{option_type}:{strike}:{expiration}"


def _strike_value(candidate: object) -> float:
    try:
        return float(getattr(candidate, "strike", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _near_duplicate_strike(candidate: object, kept: list) -> bool:
    """Reject half-strike twins (18.0 vs 18.5) on the same chain that look identical."""
    sym = str(getattr(candidate, "symbol", "") or "").upper()
    option_type = str(getattr(candidate, "option_type", "") or "").lower()
    expiration = getattr(candidate, "expiration", None)
    strike = _strike_value(candidate)
    for other in kept:
        c = other.planned.scored.candidate
        if str(c.symbol or "").upper() != sym:
            continue
        if str(c.option_type or "").lower() != option_type:
            continue
        if getattr(c, "expiration", None) != expiration:
            continue
        if abs(_strike_value(c) - strike) < 0.51:
            return True
    return False


def select_signals_to_save(
    explained: list,
    *,
    limit: int = MAX_SIGNALS_STORED,
    max_per_symbol: int = MAX_PER_SYMBOL,
) -> list:
    """Dedupe contracts, skip near-twin strikes, and cap per underlying."""
    to_save: list = []
    seen: set[str] = set()
    per_symbol: dict[str, int] = {}

    for signal in explained:
        if len(to_save) >= limit:
            break
        c = signal.planned.scored.candidate
        key = contract_identity_key(c)
        if key in seen or _near_duplicate_strike(c, to_save):
            continue
        sym = str(c.symbol or "").upper()
        if per_symbol.get(sym, 0) >= max_per_symbol:
            continue
        seen.add(key)
        per_symbol[sym] = per_symbol.get(sym, 0) + 1
        to_save.append(signal)

    # If the per-symbol cap left empty slots, fill with remaining unique contracts.
    if len(to_save) < limit:
        for signal in explained:
            if len(to_save) >= limit:
                break
            c = signal.planned.scored.candidate
            key = contract_identity_key(c)
            if key in seen or _near_duplicate_strike(c, to_save):
                continue
            seen.add(key)
            to_save.append(signal)

    return to_save


async def _yahoo_last_price(symbol: str) -> float:
    def _fetch() -> float:
        try:
            import yfinance as yf
        except Exception:
            return 0.0
        ticker = yf.Ticker(symbol.upper())
        price = getattr(ticker, "fast_info", {}).get("lastPrice")  # type: ignore[attr-defined]
        if price:
            return float(price)
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return 0.0

    return await asyncio.to_thread(_fetch)


class OptionsRefreshService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self._discovery_map: dict[str, DiscoveredSymbol] = {}

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
            logger.warning("Could not load watchlist: %s", exc)
        return symbols

    async def build_scan_universe(self) -> tuple[list[str], dict]:
        """Phase 1 — discover movers/actives across the market."""
        self._discovery_map = {}
        discovered, discovery_stats = await asyncio.to_thread(
            discover_market_symbols, max_symbols=DISCOVERY_POOL_SIZE
        )
        watchlist = await self._load_watchlist_symbols()

        for sym in watchlist:
            if sym not in self._discovery_map:
                self._discovery_map[sym] = DiscoveredSymbol(symbol=sym, sources=["watchlist"])
            elif "watchlist" not in self._discovery_map[sym].sources:
                self._discovery_map[sym].sources.append("watchlist")

        for entry in discovered:
            self._discovery_map[entry.symbol] = entry

        ranked = sorted(
            self._discovery_map.values(),
            key=lambda e: (pre_score_symbol(e), "watchlist" in e.sources),
            reverse=True,
        )
        deep_dive = [e.symbol for e in ranked[:DEEP_DIVE_SYMBOL_LIMIT]]

        stats = {
            "discovery": discovery_stats,
            "watchlist_symbols": len(watchlist),
            "universe_size": len(self._discovery_map),
            "deep_dive_symbols": len(deep_dive),
        }
        return deep_dive, stats

    async def _fetch_symbol_candidates(
        self,
        symbol: str,
        finnhub: FinnhubClient | None,
        *,
        with_finnhub: bool = True,
    ) -> tuple[list, dict]:
        errors: list[str] = []
        discovery = self._discovery_map.get(symbol)
        stock_context: dict = {
            "price": 0,
            "relative_volume": 1.0,
            "trend_bullish": True,
            "has_catalyst": False,
            "discovery_sources": discovery.sources if discovery else [],
            "day_change_pct": discovery.change_pct if discovery else None,
        }

        if finnhub and with_finnhub:
            try:
                stock_context = await finnhub.get_stock_context(symbol)
                stock_context["discovery_sources"] = discovery.sources if discovery else []
                stock_context["day_change_pct"] = discovery.change_pct if discovery else None
            except FinnhubError as exc:
                errors.append(f"{symbol}: {exc}")

        if float(stock_context.get("price") or 0) <= 0:
            try:
                stock_context["price"] = await _yahoo_last_price(symbol)
            except Exception as exc:
                errors.append(f"{symbol} price: {exc}")
                return [], {"errors": errors}

        if discovery and discovery.change_pct is not None:
            if discovery.change_pct <= -1.5 and "day_losers" in discovery.sources:
                stock_context.setdefault("trend_bullish", False)
            elif discovery.change_pct >= 1.5 and "day_gainers" in discovery.sources:
                stock_context.setdefault("trend_bullish", True)

        try:
            contracts = await asyncio.to_thread(fetch_options_candidates, symbol, stock_context)
        except Exception as exc:
            errors.append(f"{symbol} options: {exc}")
            return [], {"errors": errors}

        return contracts, {"errors": errors}

    async def gather_live_candidates(self, symbols: list[str] | None = None) -> tuple[list, dict]:
        """Phase 2 — deep dive options chains on the best universe."""
        if symbols is None:
            symbols, discovery_stats = await self.build_scan_universe()
        else:
            discovery_stats = {"manual_symbols": len(symbols)}

        stats: dict = {
            "symbols_scanned": len(symbols),
            "symbols_with_data": 0,
            "raw_contracts": 0,
            "errors": [],
            "data_sources": {"options": "yahoo_finance", "stocks": "yahoo_finance"},
            **discovery_stats,
        }
        all_candidates: list = []

        finnhub: FinnhubClient | None = None
        if settings.finnhub_api_key:
            try:
                finnhub = FinnhubClient()
                stats["data_sources"]["stocks"] = "finnhub+yahoo"
            except FinnhubError as exc:
                stats["errors"].append(str(exc))

        semaphore = asyncio.Semaphore(PARALLEL_SYMBOL_FETCHES)

        async def fetch_one(index: int, symbol: str) -> tuple[list, dict]:
            async with semaphore:
                with_finnhub = finnhub is not None and index < FINNHUB_CONTEXT_LIMIT
                return await self._fetch_symbol_candidates(
                    symbol, finnhub, with_finnhub=with_finnhub
                )

        results = await asyncio.gather(
            *[fetch_one(i, symbol) for i, symbol in enumerate(symbols)],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                stats["errors"].append(str(result))
                continue
            contracts, symbol_stats = result
            stats["errors"].extend(symbol_stats.get("errors", []))
            if contracts:
                stats["symbols_with_data"] += 1
                stats["raw_contracts"] += len(contracts)
                all_candidates.extend(contracts)

        return all_candidates, stats

    async def refresh_live_options(self, *, replace: bool = True, limit: int = MAX_SIGNALS_OUTPUT) -> dict:
        from app.services.calibration_service import CalibrationService

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments()
        min_prob = float(calibration.get("options_min_profit_probability", 52.0))
        min_opp = float(calibration.get("options_min_opportunity", 45.0))
        budget_first = bool(calibration.get("options_budget_first", True))

        candidates, stats = await self.gather_live_candidates()
        explained = run_options_pipeline(candidates)
        pipeline_count = len(explained)

        explained = [
            s
            for s in explained
            if float((s.planned.scored.scoring_snapshot or {}).get("profit_probability") or 0) >= min_prob
            and float(s.planned.scored.opportunity_score or 0) >= min_opp
        ]
        after_calibration = len(explained)

        if not explained:
            return {
                "signals_created": 0,
                "filtered_out": stats["raw_contracts"],
                "symbols_scanned": stats.get("symbols_scanned", 0),
                "stats": {
                    **stats,
                    "pipeline_count": pipeline_count,
                    "after_calibration": 0,
                    "budget_first_mode": budget_first,
                },
                "used_mock_fallback": False,
                "message": (
                    f"Scanned {stats['symbols_scanned']} symbols — no liquid setups passed filters. "
                    "Try again during market hours."
                ),
            }

        for signal in explained:
            snap = signal.planned.scored.scoring_snapshot or {}
            premium = signal.planned.scored.candidate.premium or 0
            snap["contract_cost"] = round(premium * 100, 2)
            snap["is_budget"] = is_budget_contract(signal.planned.scored.candidate)
            snap["budget_first_mode"] = budget_first
            signal.planned.scored.scoring_snapshot = snap

        # Capital preservation: under-$100 first until options win rate is proven.
        def _rank_key(signal: object) -> tuple[float, float, float]:
            scored = signal.planned.scored  # type: ignore[attr-defined]
            snap = scored.scoring_snapshot or {}
            prob = float(snap.get("profit_probability") or 0)
            budget = 1.0 if is_budget_contract(scored.candidate) else 0.0
            if budget_first:
                return (budget, prob, float(scored.opportunity_score or 0))
            return (prob, budget, float(scored.opportunity_score or 0))

        explained.sort(key=_rank_key, reverse=True)

        budget_pool = [s for s in explained if is_budget_contract(s.planned.scored.candidate)]
        if budget_first:
            if budget_pool:
                explained = budget_pool
            else:
                # No sub-$100 liquid contracts — surface the cheapest few only.
                explained = sorted(
                    explained,
                    key=lambda s: contract_cost(s.planned.scored.candidate),
                )[: max(limit, 8)]
                for signal in explained:
                    snap = signal.planned.scored.scoring_snapshot or {}
                    snap["budget_fallback"] = True
                    signal.planned.scored.scoring_snapshot = snap

        standard = explained[:limit]
        budget = budget_pool[:MAX_BUDGET_SIGNALS]

        to_save = select_signals_to_save(explained, limit=MAX_SIGNALS_STORED)

        stats["pipeline_count"] = pipeline_count
        stats["after_calibration"] = after_calibration
        stats["budget_candidates"] = len(budget_pool)
        stats["budget_saved"] = len(
            [s for s in to_save if is_budget_contract(s.planned.scored.candidate)]
        )
        stats["budget_first_mode"] = budget_first
        stats["options_proven"] = bool(calibration.get("options_proven"))
        stats["symbols_saved"] = len(
            {s.planned.scored.candidate.symbol for s in to_save}
        )

        if replace:
            await self.db.delete(
                "options_signals",
                {"user_id": f"eq.{self.user_id}", "status": "eq.active"},
            )

        rows = [explained_to_options_row(self.user_id, s) for s in to_save]
        saved = await self.db.insert("options_signals", rows) if rows else []

        if saved:
            from app.services.alert_service import AlertService
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("options", saved)
            await AlertService(self.db, self.user_id).notify_high_score_signals(
                "options",
                saved,
                title_fn=lambda s: f"Options play · {s.get('underlying')} ({float(s.get('opportunity_score') or 0):.0f}/100)",
            )

        top_prob = None
        if standard:
            snap = standard[0].planned.scored.scoring_snapshot or {}
            top_prob = snap.get("profit_probability")

        mode_note = None
        if budget_first:
            decided = int(calibration.get("options_decided") or 0)
            wr = calibration.get("options_win_rate")
            wr_label = f"{float(wr):.0f}%" if wr is not None else "n/a"
            mode_note = (
                f"Capital-first mode: showing under-$100 contracts "
                f"({decided} graded · {wr_label} win rate). "
                f"Higher-cost plays unlock after {15}+ graded at ≥55%."
            )

        return {
            "signals_created": len(saved),
            "standard_signals": len(standard),
            "budget_signals": len(budget),
            "filtered_out": max(stats["raw_contracts"] - after_calibration, 0),
            "symbols_scanned": stats.get("symbols_scanned", 0),
            "stats": stats,
            "used_mock_fallback": False,
            "top_profit_probability": top_prob,
            "calibration": calibration,
            "budget_first": budget_first,
            "message": mode_note,
        }
