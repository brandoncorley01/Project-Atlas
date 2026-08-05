"""Build a real equity market heatmap universe from Yahoo screeners + quotes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.market_intelligence.freshness import build_freshness, utcnow
from app.market_intelligence.heatmap import SECTOR_MAP, build_market_heatmap
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)

# Broader sector coverage for heatmap tiles.
_EQUITY_SECTOR_MAP: dict[str, str] = {
    **SECTOR_MAP,
    "AVGO": "Technology",
    "ORCL": "Technology",
    "CRM": "Technology",
    "INTC": "Technology",
    "MU": "Technology",
    "PLTR": "Technology",
    "UBER": "Consumer",
    "COST": "Consumer",
    "WMT": "Consumer",
    "HD": "Consumer",
    "DIS": "Communication",
    "BAC": "Financials",
    "WFC": "Financials",
    "GS": "Financials",
    "V": "Financials",
    "MA": "Financials",
    "LLY": "Health Care",
    "ABBV": "Health Care",
    "PFE": "Health Care",
    "MRK": "Health Care",
    "XLE": "Energy",
    "COP": "Energy",
    "BA": "Industrials",
    "CAT": "Industrials",
    "GE": "Industrials",
    "UNP": "Industrials",
    "NEE": "Utilities",
    "LIN": "Materials",
    "DIA": "Index",
}


def _enrich_market_caps(symbols: list[str]) -> dict[str, float]:
    """Best-effort market cap from yfinance fast_info (sync). Kept for optional use."""
    out: dict[str, float] = {}
    try:
        import yfinance as yf
    except Exception:
        return out

    for sym in symbols:
        try:
            t = yf.Ticker(sym.replace(".", "-"))
            fast = getattr(t, "fast_info", None)
            cap = None
            if fast is not None:
                if hasattr(fast, "get"):
                    cap = fast.get("market_cap") or fast.get("marketCap")
                if cap is None:
                    cap = getattr(fast, "market_cap", None) or getattr(fast, "marketCap", None)
            if cap is None:
                info = getattr(t, "info", None) or {}
                if isinstance(info, dict):
                    cap = info.get("marketCap")
            if cap:
                out[sym] = float(cap)
        except Exception as exc:
            logger.debug("market cap skip %s: %s", sym, exc)
    return out


# Stable relative weights so the treemap still reads as mega vs mid without slow cap lookups.
_CAP_PROXY: dict[str, float] = {
    "AAPL": 3.4e12,
    "MSFT": 3.2e12,
    "NVDA": 3.0e12,
    "AMZN": 2.2e12,
    "GOOGL": 2.1e12,
    "META": 1.5e12,
    "TSLA": 1.1e12,
    "BRK-B": 1.0e12,
    "AVGO": 9e11,
    "JPM": 7e11,
    "V": 6e11,
    "MA": 5e11,
    "SPY": 5e11,
    "QQQ": 3e11,
    "IWM": 8e10,
}


def _proxy_market_caps(
    symbols: list[str],
    quotes: dict[str, dict[str, Any]],
    discovered: list[Any],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for i, sym in enumerate(symbols):
        if sym in _CAP_PROXY:
            out[sym] = _CAP_PROXY[sym]
            continue
        price = float((quotes.get(sym) or {}).get("price") or 0)
        # Rank-based fallback keeps tiles visible and relatively sized
        out[sym] = max(price * 1e9, 5e10) * (1.0 - i * 0.01)
        match = next((d for d in discovered if getattr(d, "symbol", None) == sym), None)
        if match is not None and getattr(match, "market_cap", None):
            try:
                out[sym] = float(match.market_cap)
            except (TypeError, ValueError):
                pass
    return out


async def build_equity_market_heatmap(
    *,
    size_by: str = "market_cap",
    color_by: str = "daily_return",
    max_symbols: int = 36,
) -> dict[str, Any]:
    """
    Real stock-market heatmap: liquid + screener symbols sized by market-cap proxy,
    colored by daily % change. Always delayed (Yahoo/Finnhub quotes) — never live.
    """
    from app.providers.market.universe import CORE_LIQUID, discover_market_symbols
    from app.providers.stocks.quotes import fetch_stock_quotes

    discovered, stats = await asyncio.to_thread(discover_market_symbols, max_symbols=max_symbols)
    symbols = [d.symbol for d in discovered] or list(CORE_LIQUID)
    # Prefer core liquid first for stable treemap
    ordered = list(dict.fromkeys([*CORE_LIQUID, *symbols]))[:max_symbols]

    quotes = await fetch_stock_quotes(ordered)
    # Skip per-symbol yfinance market-cap calls — they blow past BFF budgets.
    # Size tiles with a stable proxy from price + known mega-cap bias.
    caps = _proxy_market_caps(ordered, quotes, discovered)

    universe: list[dict[str, Any]] = []
    for sym in ordered:
        q = quotes.get(sym) or {}
        change_pct = q.get("change_pct")
        if change_pct is None:
            # Fall back to screener-discovered change when quote missing
            match = next((d for d in discovered if d.symbol == sym), None)
            change_pct = match.change_pct if match else None
        if change_pct is None and not q:
            continue
        price = float(q.get("price") or 0)
        market_cap = caps.get(sym) or (abs(float(change_pct or 0)) + 1) * 1e9
        universe.append(
            {
                "symbol": sym,
                "sector": _EQUITY_SECTOR_MAP.get(sym, SECTOR_MAP.get(sym, "Other")),
                "industry": "Equity",
                "market_cap": market_cap,
                "volume": 1,
                "dollar_volume": price * 1_000_000 if price else market_cap / 100,
                "daily_return": float(change_pct or 0),
                "price": price or None,
                "change": q.get("change"),
                "momentum_score": float(change_pct or 0) / 10.0,
                "options_bias": 0.0,
            }
        )

    if not universe:
        # Absolute last resort — still labelled simulated
        universe = [
            {"symbol": s, "sector": _EQUITY_SECTOR_MAP.get(s, "Other"), "market_cap": 1e11, "daily_return": 0.0}
            for s in CORE_LIQUID[:12]
        ]
        status = DataStatus.SIMULATED
        provider = "equity_heatmap_fallback"
        missing = ["live_quotes"]
    else:
        status = DataStatus.DELAYED
        provider = "yahoo_equity_quotes"
        missing = []

    payload = build_market_heatmap(universe, size_by=size_by, color_by=color_by)
    # Attach % labels suited to daily returns
    for sector in payload.get("sectors") or []:
        for tile in sector.get("tiles") or []:
            ret = float(tile.get("daily_return") or tile.get("color_value") or 0)
            tile["label"] = _return_label(ret)
            tile["why"] = f"{ret:+.2f}% today"
    for tile in payload.get("table_fallback") or []:
        ret = float(tile.get("daily_return") or tile.get("color_value") or 0)
        tile["label"] = _return_label(ret)
        tile["action"] = f"{ret:+.2f}%"

    payload["freshness"] = build_freshness(
        provider_name=provider,
        data_timestamp=utcnow(),
        data_status=status,
        missing_fields=missing,
    ).to_dict()
    payload["disclaimer"] = (
        "Equity market heatmap from delayed Yahoo/Finnhub quotes and screeners. "
        "Not a live tape. Describes recent session moves — not a forecast."
    )
    payload["universe_stats"] = stats
    payload["symbol_count"] = len(universe)
    payload["heatmap_kind"] = "equity"
    return payload


def _return_label(pct: float) -> str:
    if pct >= 3:
        return "Strong up"
    if pct >= 1:
        return "Up"
    if pct >= 0.25:
        return "Slightly up"
    if pct <= -3:
        return "Strong down"
    if pct <= -1:
        return "Down"
    if pct <= -0.25:
        return "Slightly down"
    return "Flat"
