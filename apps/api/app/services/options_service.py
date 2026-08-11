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


def symbol_expiration_key(candidate: object) -> str:
    """One directional thesis per underlying + expiration."""
    symbol = str(getattr(candidate, "symbol", "") or "").upper()
    expiration = getattr(candidate, "expiration", None)
    return f"{symbol}:{expiration}"


def _strike_value(candidate: object) -> float:
    try:
        return float(getattr(candidate, "strike", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _option_type(candidate: object) -> str:
    return str(getattr(candidate, "option_type", "") or "").lower()


def _signal_direction_rank(signal: object) -> tuple[float, float, float]:
    """Higher = more confident directional pick (confidence, win odds, opportunity)."""
    scored = signal.planned.scored  # type: ignore[attr-defined]
    snap = scored.scoring_snapshot or {}
    return (
        float(getattr(scored, "confidence_score", 0) or 0),
        float(snap.get("profit_probability") or 0),
        float(getattr(scored, "opportunity_score", 0) or 0),
    )


def build_hedge_strategy(signal: object) -> dict:
    """Compact opposite-side contract snapshot nested under the primary pick."""
    scored = signal.planned.scored  # type: ignore[attr-defined]
    c = scored.candidate
    snap = scored.scoring_snapshot or {}
    premium = float(getattr(c, "premium", 0) or 0)
    contract_cost = snap.get("contract_cost")
    if contract_cost is None:
        contract_cost = round(premium * 100, 2)
    expiration = getattr(c, "expiration", None)
    return {
        "role": "opposite_side_hedge",
        "option_type": _option_type(c),
        "strike": _strike_value(c),
        "expiration": expiration.isoformat() if hasattr(expiration, "isoformat") else expiration,
        "premium": premium,
        "contract_cost": float(contract_cost or 0),
        "confidence_score": float(getattr(scored, "confidence_score", 0) or 0),
        "risk_score": float(getattr(scored, "risk_score", 0) or 0),
        "opportunity_score": float(getattr(scored, "opportunity_score", 0) or 0),
        "profit_probability": float(snap.get("profit_probability") or 0),
        "delta": getattr(c, "delta", None),
        "bid": getattr(c, "bid", None),
        "ask": getattr(c, "ask", None),
        "rationale": (
            "Same-expiry opposite side — Atlas's hedge if the primary directional thesis fails."
        ),
    }


def attach_hedge_strategy(primary: object, members: list) -> None:
    """Nest the best opposite-side same-expiry contract under the primary pick."""
    primary_type = _option_type(primary.planned.scored.candidate)  # type: ignore[attr-defined]
    opposite = "put" if primary_type == "call" else "call"
    hedges = [
        s
        for s in members
        if s is not primary and _option_type(s.planned.scored.candidate) == opposite
    ]
    scored = primary.planned.scored  # type: ignore[attr-defined]
    snap = dict(scored.scoring_snapshot or {})
    if not hedges:
        snap.pop("hedge_strategy", None)
        scored.scoring_snapshot = snap
        return
    hedge = max(hedges, key=_signal_direction_rank)
    snap["hedge_strategy"] = build_hedge_strategy(hedge)
    scored.scoring_snapshot = snap


def choose_primary_per_expiration(explained: list) -> list:
    """One confident direction per symbol+expiry; opposite side becomes a hedge."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for signal in explained:
        key = symbol_expiration_key(signal.planned.scored.candidate)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(signal)

    primaries: list = []
    for key in order:
        members = groups[key]
        primary = max(members, key=_signal_direction_rank)
        attach_hedge_strategy(primary, members)
        primaries.append(primary)
    return primaries


def _near_duplicate_strike(candidate: object, kept: list) -> bool:
    """Reject half-strike twins (18.0 vs 18.5) on the same chain that look identical."""
    sym = str(getattr(candidate, "symbol", "") or "").upper()
    option_type = _option_type(candidate)
    expiration = getattr(candidate, "expiration", None)
    strike = _strike_value(candidate)
    for other in kept:
        c = other.planned.scored.candidate
        if str(c.symbol or "").upper() != sym:
            continue
        if _option_type(c) != option_type:
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
    """Pick one direction per expiry, attach hedges, then diversify across underlyings."""
    # Collapse call+put on the same expiry into a primary + nested hedge first.
    directional = choose_primary_per_expiration(explained)

    to_save: list = []
    seen: set[str] = set()
    seen_expiry: set[str] = set()
    per_symbol: dict[str, int] = {}

    for signal in directional:
        if len(to_save) >= limit:
            break
        c = signal.planned.scored.candidate
        key = contract_identity_key(c)
        expiry_key = symbol_expiration_key(c)
        if key in seen or expiry_key in seen_expiry or _near_duplicate_strike(c, to_save):
            continue
        sym = str(c.symbol or "").upper()
        if per_symbol.get(sym, 0) >= max_per_symbol:
            continue
        seen.add(key)
        seen_expiry.add(expiry_key)
        per_symbol[sym] = per_symbol.get(sym, 0) + 1
        to_save.append(signal)

    # If the per-symbol cap left empty slots, fill with remaining unique expiries.
    if len(to_save) < limit:
        for signal in directional:
            if len(to_save) >= limit:
                break
            c = signal.planned.scored.candidate
            key = contract_identity_key(c)
            expiry_key = symbol_expiration_key(c)
            if key in seen or expiry_key in seen_expiry or _near_duplicate_strike(c, to_save):
                continue
            seen.add(key)
            seen_expiry.add(expiry_key)
            to_save.append(signal)

    return to_save


async def _yahoo_quote(symbol: str) -> dict[str, float]:
    """Price + session change from Yahoo (sync via thread)."""

    def _fetch() -> dict[str, float]:
        try:
            import yfinance as yf
        except Exception:
            return {}
        try:
            ticker = yf.Ticker(symbol.upper())
            fast = getattr(ticker, "fast_info", None)
            price = 0.0
            prev = 0.0
            if fast is not None:
                if hasattr(fast, "get"):
                    price = float(fast.get("lastPrice") or fast.get("last_price") or 0)
                    prev = float(fast.get("previousClose") or fast.get("previous_close") or 0)
                else:
                    price = float(getattr(fast, "last_price", 0) or getattr(fast, "lastPrice", 0) or 0)
                    prev = float(
                        getattr(fast, "previous_close", 0) or getattr(fast, "previousClose", 0) or 0
                    )
            if price <= 0:
                hist = ticker.history(period="5d", interval="1d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    if len(hist) > 1:
                        prev = float(hist["Close"].iloc[-2])
            if price <= 0:
                return {}
            change = price - prev if prev > 0 else 0.0
            change_pct = (change / prev) * 100 if prev > 0 else 0.0
            out: dict[str, float] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
            if prev > 0:
                out["previous_close"] = round(prev, 2)
            return out
        except Exception:
            return {}

    return await asyncio.to_thread(_fetch)


async def _yahoo_last_price(symbol: str) -> float:
    q = await _yahoo_quote(symbol)
    return float(q.get("price") or 0)


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

        need_yahoo = (
            float(stock_context.get("price") or 0) <= 0
            or stock_context.get("day_change_pct") is None
            or not stock_context.get("previous_close")
        )
        if need_yahoo:
            try:
                yq = await _yahoo_quote(symbol)
                if yq.get("price") and float(stock_context.get("price") or 0) <= 0:
                    stock_context["price"] = yq["price"]
                if stock_context.get("day_change_pct") is None and yq.get("change_pct") is not None:
                    stock_context["day_change_pct"] = yq["change_pct"]
                if yq.get("previous_close") and not stock_context.get("previous_close"):
                    stock_context["previous_close"] = yq["previous_close"]
            except Exception as exc:
                errors.append(f"{symbol} price: {exc}")
                if float(stock_context.get("price") or 0) <= 0:
                    return [], {"errors": errors}

        # Prefer quote/screener session move over a blanket bullish default.
        # setdefault was wrong here — the initial dict already set trend_bullish=True.
        change = stock_context.get("day_change_pct")
        if change is None and discovery is not None:
            change = discovery.change_pct
        try:
            change_f = float(change) if change is not None else None
        except (TypeError, ValueError):
            change_f = None
        if change_f is not None:
            stock_context["day_change_pct"] = change_f
            stock_context["trend_bullish"] = change_f >= 0
        elif discovery and "day_losers" in (discovery.sources or []):
            stock_context["trend_bullish"] = False
        elif discovery and "day_gainers" in (discovery.sources or []):
            stock_context["trend_bullish"] = True

        # If we still have no price from Finnhub/Yahoo, stop — empty chain.
        if float(stock_context.get("price") or 0) <= 0:
            return [], {"errors": errors or [f"{symbol}: no price"]}

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
            # Grade ready picks from durable performance rows before wiping the board.
            try:
                from app.services.outcome_resolver import OutcomeResolverService

                await OutcomeResolverService(self.db, self.user_id).resolve_pending(
                    limit=40,
                    module="options",
                )
            except Exception as exc:
                logger.warning("Pre-replace options auto-grade skipped: %s", exc)
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
