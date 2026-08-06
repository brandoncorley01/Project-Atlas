"""Yahoo-backed earnings calendar, quotes, and options chain context."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from app.market_intelligence.earnings.types import (
    ContractCandidate,
    EarningsEvent,
    EarningsPhase,
)
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)

# ETFs/indexes rarely have company earnings calendars — skip noisy 404s.
_SKIP_EARNINGS_CALENDAR = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "XLE",
        "XLF",
        "XLK",
        "XLV",
        "XLI",
        "XLP",
        "XLU",
        "XLB",
        "XLRE",
        "XLC",
        "HYG",
        "TLT",
        "GLD",
        "SLV",
    }
)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (list, tuple)) and value:
        return _as_date(value[0])
    try:
        if hasattr(value, "date") and callable(value.date):
            return value.date()
    except Exception:
        pass
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value[:10], fmt).date()
            except ValueError:
                continue
    return None


def _phase_for(report_date: date, today: date | None = None) -> EarningsPhase:
    today = today or date.today()
    delta = (report_date - today).days
    if delta > 1:
        return EarningsPhase.PRE_EARNINGS
    if delta >= 0:
        return EarningsPhase.WAITING_FOR_REPORT
    if delta >= -1:
        return EarningsPhase.POST_RELEASE_UNCONFIRMED
    if delta >= -5:
        return EarningsPhase.POST_EARNINGS_CONFIRMED
    return EarningsPhase.EXPIRED


def _moneyness(option_type: str, strike: float, spot: float) -> str:
    if spot <= 0:
        return "atm"
    if option_type == "call":
        if strike < spot * 0.98:
            return "itm"
        if strike > spot * 1.02:
            return "otm"
        return "atm"
    if strike > spot * 1.02:
        return "itm"
    if strike < spot * 0.98:
        return "otm"
    return "atm"


def _spread_pct(bid: float | None, ask: float | None, premium: float) -> float:
    if bid and ask and bid > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid > 0:
            return round(((ask - bid) / mid) * 100.0, 2)
    return 12.0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        n = float(value)
        if math.isnan(n):
            return None
        return n
    except (TypeError, ValueError):
        return None


def _universe(limit: int = 40) -> list[str]:
    try:
        from app.providers.market.universe import CORE_LIQUID, discover_market_symbols

        discovered, _ = discover_market_symbols(max_symbols=limit)
        return list(dict.fromkeys([*CORE_LIQUID, *[d.symbol for d in discovered]]))[:limit]
    except Exception:
        return [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "META",
            "GOOGL",
            "TSLA",
            "AMD",
            "JPM",
            "XOM",
            "COST",
            "AVGO",
            "NFLX",
            "CRM",
            "INTC",
        ]


def _calendar_row(symbol: str) -> dict[str, Any] | None:
    import yfinance as yf

    try:
        cal = yf.Ticker(symbol).calendar
    except Exception as exc:
        logger.debug("calendar fail %s: %s", symbol, exc)
        return None
    if not isinstance(cal, dict):
        return None
    report = _as_date(cal.get("Earnings Date") or cal.get("earningsDate"))
    if report is None:
        return None
    return {
        "report_date": report,
        "eps_estimate": _safe_float(cal.get("Earnings Average")),
        "revenue_estimate": _safe_float(cal.get("Revenue Average")),
        "company_name": symbol,
    }


def _historical_moves(symbol: str, lookback: int = 4) -> list[float]:
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 10:
            return []
        rets = hist["Close"].pct_change().dropna().abs() * 100.0
        top = sorted((float(x) for x in rets.tolist()), reverse=True)[:lookback]
        return [round(x, 2) for x in top if x > 0]
    except Exception as exc:
        logger.debug("hist moves fail %s: %s", symbol, exc)
        return []


def _build_chain(symbol: str, price: float, *, report_date: date | None = None) -> dict[str, Any] | None:
    from app.providers.options.yahoo import fetch_options_candidates

    if price <= 0:
        return None
    # Widen DTE window so near-earnings names still find listed expirations.
    max_dte = 28
    if report_date is not None:
        days_out = (report_date - date.today()).days
        max_dte = max(28, min(60, days_out + 21))
    try:
        candidates = fetch_options_candidates(
            symbol,
            {"price": price},
            min_dte=1,
            max_dte=max_dte,
            max_expirations=5,
        )
    except Exception as exc:
        logger.debug("chain fail %s: %s", symbol, exc)
        return None
    if not candidates:
        return None

    calls = [c for c in candidates if c.option_type == "call"]
    puts = [c for c in candidates if c.option_type == "put"]
    atm_call = min(calls, key=lambda c: abs(float(c.strike) - price), default=None)
    atm_put = min(puts, key=lambda c: abs(float(c.strike) - price), default=None)

    contracts: list[ContractCandidate] = []
    for c in candidates[:10]:
        bid = float(c.bid or 0)
        ask = float(c.ask or c.premium or 0)
        premium = float(c.premium or ask or bid or 0)
        if premium <= 0:
            continue
        iv_raw = float(c.implied_volatility) if c.implied_volatility is not None else None
        iv = (iv_raw / 100.0) if iv_raw is not None and iv_raw > 3 else iv_raw
        # Persist OI=0 as None so liquidity gates treat it as unknown, not illiquid.
        oi_raw = int(c.open_interest or 0)
        contracts.append(
            ContractCandidate(
                option_type=str(c.option_type),
                strike=float(c.strike),
                expiration=c.expiration.isoformat() if hasattr(c.expiration, "isoformat") else str(c.expiration),
                premium=premium,
                bid=bid if bid > 0 else max(premium * 0.97, 0.01),
                ask=ask if ask > 0 else premium,
                volume=int(c.volume or 0),
                open_interest=oi_raw if oi_raw > 0 else 0,
                iv=iv,
                delta=float(c.delta) if c.delta is not None else None,
                moneyness=_moneyness(str(c.option_type), float(c.strike), price),
                spread_pct=_spread_pct(bid if bid > 0 else None, ask if ask > 0 else None, premium),
            )
        )

    if not contracts:
        return None

    if not any(c.moneyness == "otm" for c in contracts):
        otmish = max((c for c in contracts if c.option_type == "call"), key=lambda c: c.strike, default=None)
        if otmish:
            otmish.moneyness = "otm"
    if not any(c.moneyness == "atm" for c in contracts) and atm_call:
        for c in contracts:
            if c.option_type == "call" and abs(c.strike - float(atm_call.strike)) < 1e-6:
                c.moneyness = "atm"
                break

    atm_iv = None
    if atm_call and atm_call.implied_volatility is not None:
        iv = float(atm_call.implied_volatility)
        atm_iv = iv / 100.0 if iv > 3 else iv
    else:
        ivs = [c.iv for c in contracts if c.iv]
        atm_iv = sum(ivs) / len(ivs) if ivs else None

    return {
        "atm_iv": atm_iv,
        "straddle_call_mid": float(atm_call.premium) if atm_call else None,
        "straddle_put_mid": float(atm_put.premium) if atm_put else None,
        "historical_iv_crush": None,
        "contracts": contracts,
    }


def _scan_calendars_sync(
    symbols: list[str],
    *,
    horizon_days: int,
    lookback_days: int,
) -> list[tuple[str, dict[str, Any]]]:
    today = date.today()
    dated: list[tuple[str, dict[str, Any]]] = []
    for sym in symbols:
        if sym.upper() in _SKIP_EARNINGS_CALENDAR:
            continue
        row = _calendar_row(sym)
        if not row:
            continue
        report: date = row["report_date"]
        if report < today - timedelta(days=lookback_days):
            continue
        if report > today + timedelta(days=horizon_days):
            continue
        dated.append((sym, row))
    dated.sort(key=lambda x: x[1]["report_date"])
    return dated


def _momentum_bias(change_pct: float | None) -> tuple[str, str]:
    """Soft session bias from delayed quotes — not analyst research."""
    if change_pct is None:
        return "unknown", "unknown"
    if change_pct >= 1.5:
        return "bullish", "constructive"
    if change_pct <= -1.5:
        return "bearish", "weakening"
    if abs(change_pct) >= 0.5:
        return "mixed", "mixed"
    return "mixed", "unknown"


async def fetch_live_earnings_desk(
    *,
    horizon_days: int = 45,
    lookback_days: int = 3,
    max_symbols: int = 36,
    max_evaluate: int = 12,
) -> tuple[list[EarningsEvent], dict[str, dict[str, Any]], dict[str, Any]]:
    """Load real Yahoo earnings events + option chains for scoring."""
    from app.providers.stocks.quotes import fetch_stock_quotes

    symbols = await asyncio.to_thread(_universe, max_symbols)
    dated = await asyncio.to_thread(
        _scan_calendars_sync,
        symbols,
        horizon_days=horizon_days,
        lookback_days=lookback_days,
    )
    if not dated:
        return [], {}, {
            "provider": "yahoo_earnings",
            "data_status": DataStatus.PARTIAL.value,
            "symbol_count": 0,
            "note": "No upcoming earnings in scanned universe",
        }

    # Cap evaluation set for latency — nearest reports first
    dated = dated[:max_evaluate]
    syms = [s for s, _ in dated]
    quotes = await fetch_stock_quotes(syms)

    events: list[EarningsEvent] = []
    chains: dict[str, dict[str, Any]] = {}

    for sym, row in dated:
        q = quotes.get(sym) or {}
        price = float(q.get("price") or 0)
        change_pct = q.get("change_pct")
        try:
            change_pct_f = float(change_pct) if change_pct is not None else None
        except (TypeError, ValueError):
            change_pct_f = None
        sentiment, sector_dir = _momentum_bias(change_pct_f)
        moves = await asyncio.to_thread(_historical_moves, sym)
        missing: list[str] = []
        if row.get("eps_estimate") is None:
            missing.append("eps_estimate")
        if not moves:
            missing.append("historical_moves")
        if price <= 0:
            missing.append("price")

        chain = None
        if price > 0:
            chain = await asyncio.to_thread(_build_chain, sym, price, report_date=row["report_date"])
        if not chain:
            missing.append("options_chain")
        else:
            chains[sym] = chain

        events.append(
            EarningsEvent(
                symbol=sym,
                company_name=str(row.get("company_name") or sym),
                report_date=row["report_date"],
                release_time="unknown",
                phase=_phase_for(row["report_date"]),
                eps_estimate=row.get("eps_estimate"),
                revenue_estimate=row.get("revenue_estimate"),
                guidance_note=None,
                analyst_sentiment=sentiment,
                sector=None,
                sector_direction=sector_dir,
                market_direction="unknown",
                price=price or None,
                volume=None,
                support=price * 0.96 if price else None,
                resistance=price * 1.04 if price else None,
                historical_moves_pct=moves,
                data_status=DataStatus.DELAYED.value,
                data_source="yahoo_earnings",
                missing_fields=missing,
                stale=False,
            )
        )

    return events, chains, {
        "provider": "yahoo_earnings",
        "data_status": DataStatus.DELAYED.value,
        "symbol_count": len(events),
        "with_chains": len(chains),
        "note": "Yahoo calendar + quotes + option chains (delayed).",
    }
