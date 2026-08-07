from __future__ import annotations

from datetime import date, datetime
from typing import Any

import math

from app.engine.models import CandidateOpportunity, SignalModule
from app.providers.options.greeks import estimate_delta

MIN_DTE = 3
MAX_DTE = 28
# Wider OTM reach for developing setups; deep ITM is filtered separately.
STRIKE_RANGE_OTM_PCT = 0.10
# Allow only tiny ITM (noise / rounding) — not already-winning opens.
STRIKE_RANGE_ITM_PCT = 0.015
MAX_CANDIDATES_PER_SYMBOL = 24


def _parse_expiration(exp_str: str) -> date:
    return datetime.strptime(exp_str, "%Y-%m-%d").date()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    return int(_safe_float(value, float(default)))


def _strike_in_developing_band(
    option_type: str,
    strike: float,
    spot: float,
    *,
    otm_pct: float = STRIKE_RANGE_OTM_PCT,
    itm_pct: float = STRIKE_RANGE_ITM_PCT,
) -> bool:
    """Prefer ATM → modest OTM; reject deep ITM that already won the move."""
    if spot <= 0 or strike <= 0:
        return False
    if option_type == "call":
        # Calls: strike above spot (OTM) up to otm_pct, or barely below (tiny ITM).
        return spot * (1 - itm_pct) <= strike <= spot * (1 + otm_pct)
    # Puts: strike below spot (OTM) down to otm_pct, or barely above (tiny ITM).
    return spot * (1 - otm_pct) <= strike <= spot * (1 + itm_pct)


def _setup_priority(candidate: CandidateOpportunity) -> tuple[int, int, int]:
    """Rank pool toward developing ATM–OTM before liquidity sort."""
    stock_price = float((candidate.metadata or {}).get("stock_price") or 0)
    strike = float(candidate.strike or 0)
    if stock_price <= 0 or strike <= 0:
        return (0, int(candidate.open_interest or 0), int(candidate.volume or 0))
    if candidate.option_type == "call":
        otm = (strike - stock_price) / stock_price * 100
    else:
        otm = (stock_price - strike) / stock_price * 100
    # Sweet developing band: 0.5–5% OTM
    if 0.5 <= otm <= 5.0:
        band = 3
    elif 0 <= otm < 0.5 or 5.0 < otm <= 8.0:
        band = 2
    elif -1.5 <= otm < 0:
        band = 1
    else:
        band = 0
    return (band, int(candidate.open_interest or 0), int(candidate.volume or 0))


def _row_to_candidate(
    symbol: str,
    option_type: str,
    row: Any,
    expiration: date,
    stock_context: dict[str, Any],
) -> CandidateOpportunity | None:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    last = _safe_float(row.get("lastPrice"))

    if ask <= 0 and last > 0:
        ask = last
    if bid <= 0 and last > 0:
        bid = last

    premium = ask if ask > 0 else (last if last > 0 else None)
    if premium is None or premium <= 0:
        return None

    volume = _safe_int(row.get("volume"))
    oi = _safe_int(row.get("openInterest"))
    iv = row.get("impliedVolatility")
    iv_val = _safe_float(iv) if iv is not None else 0
    iv_pct = iv_val * 100 if iv_val > 0 else None
    stock_price = float(stock_context.get("price") or 0)
    strike = float(row["strike"])
    delta = estimate_delta(option_type, strike, stock_price)

    return CandidateOpportunity(
        module=SignalModule.OPTIONS,
        symbol=symbol.upper(),
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        premium=round(premium, 2),
        bid=round(bid, 2) if bid else None,
        ask=round(ask, 2) if ask else None,
        volume=volume,
        open_interest=oi,
        delta=delta,
        implied_volatility=iv_pct,
        relative_volume=float(stock_context.get("relative_volume") or 1.0),
        has_catalyst=bool(stock_context.get("has_catalyst")),
        trend_bullish=bool(stock_context.get("trend_bullish")),
        metadata={
            "source": "yahoo_finance",
            "stock_price": stock_context.get("price"),
            "previous_close": stock_context.get("previous_close"),
            "rsi": stock_context.get("rsi"),
            "news_count": stock_context.get("news_count"),
            "top_headline": stock_context.get("top_headline"),
            "catalyst_impact": stock_context.get("catalyst_impact"),
            "catalyst_sentiment": stock_context.get("catalyst_sentiment"),
            "stock_data_source": stock_context.get("data_source", "yahoo"),
            "discovery_sources": stock_context.get("discovery_sources", []),
            "day_change_pct": stock_context.get("day_change_pct"),
        },
    )


def _candidate_liquid_enough(candidate: CandidateOpportunity) -> bool:
    """Yahoo often reports openInterest=0 even on liquid names — accept volume as proxy."""
    oi = int(candidate.open_interest or 0)
    vol = int(candidate.volume or 0)
    if oi >= 50:
        return True
    if oi == 0 and vol >= 50:
        return True
    if vol >= 200:
        return True
    return False


def fetch_options_candidates(
    symbol: str,
    stock_context: dict[str, Any],
    *,
    min_dte: int = MIN_DTE,
    max_dte: int = MAX_DTE,
    max_expirations: int = 3,
) -> list[CandidateOpportunity]:
    """Fetch liquid ATM–modest-OTM contracts via Yahoo Finance (free, no API key).

    Strike window is asymmetric: hunt setups that still need the move to finish,
    not contracts that were already ITM after the open gap.
    """
    stock_price = float(stock_context.get("price") or 0)
    if stock_price <= 0:
        return []

    try:
        import yfinance as yf
    except Exception:
        return []

    ticker = yf.Ticker(symbol.upper())
    try:
        expirations = list(ticker.options or [])
    except Exception:
        return []

    pool: list[CandidateOpportunity] = []
    today = date.today()

    # Cap expirations scanned — full chain walks blow MI latency budgets
    scanned = 0
    for exp_str in expirations:
        try:
            expiration = _parse_expiration(exp_str)
        except ValueError:
            continue

        dte = (expiration - today).days
        if dte < min_dte or dte > max_dte:
            continue
        if scanned >= max_expirations:
            break
        scanned += 1

        try:
            chain = ticker.option_chain(exp_str)
        except Exception:
            continue

        for option_type, frame in (("call", chain.calls), ("put", chain.puts)):
            if frame is None or frame.empty:
                continue

            # Rough pre-filter then apply developing-band check per row.
            lo = stock_price * (1 - max(STRIKE_RANGE_OTM_PCT, STRIKE_RANGE_ITM_PCT))
            hi = stock_price * (1 + max(STRIKE_RANGE_OTM_PCT, STRIKE_RANGE_ITM_PCT))
            near_money = frame[(frame["strike"] >= lo) & (frame["strike"] <= hi)]

            for _, row in near_money.iterrows():
                strike = _safe_float(row.get("strike"))
                if not _strike_in_developing_band(option_type, strike, stock_price):
                    continue
                candidate = _row_to_candidate(symbol, option_type, row, expiration, stock_context)
                if candidate and _candidate_liquid_enough(candidate):
                    pool.append(candidate)

    pool.sort(key=_setup_priority, reverse=True)
    return pool[:MAX_CANDIDATES_PER_SYMBOL]
