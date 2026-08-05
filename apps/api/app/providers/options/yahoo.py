from __future__ import annotations

from datetime import date, datetime
from typing import Any

import math

from app.engine.models import CandidateOpportunity, SignalModule
from app.providers.options.greeks import estimate_delta

MIN_DTE = 3
MAX_DTE = 28
STRIKE_RANGE_PCT = 0.15
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


def fetch_options_candidates(
    symbol: str,
    stock_context: dict[str, Any],
) -> list[CandidateOpportunity]:
    """Fetch liquid near-the-money contracts via Yahoo Finance (free, no API key)."""
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
        if dte < MIN_DTE or dte > MAX_DTE:
            continue
        if scanned >= 3:
            break
        scanned += 1

        try:
            chain = ticker.option_chain(exp_str)
        except Exception:
            continue

        for option_type, frame in (("call", chain.calls), ("put", chain.puts)):
            if frame is None or frame.empty:
                continue

            near_money = frame[
                (frame["strike"] >= stock_price * (1 - STRIKE_RANGE_PCT))
                & (frame["strike"] <= stock_price * (1 + STRIKE_RANGE_PCT))
            ]

            for _, row in near_money.iterrows():
                candidate = _row_to_candidate(symbol, option_type, row, expiration, stock_context)
                if candidate and candidate.open_interest >= 50:
                    pool.append(candidate)

    pool.sort(key=lambda c: (c.open_interest, c.volume), reverse=True)
    return pool[:MAX_CANDIDATES_PER_SYMBOL]
