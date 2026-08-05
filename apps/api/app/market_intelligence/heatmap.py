"""Heatmap aggregation helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.market_intelligence.scoring.options_activity import score_options_activity
from app.market_intelligence.scoring.sector_rotation import classify_sector
from app.market_intelligence.types import NormalizedOptionsActivity


# Lightweight sector map for MVP when full universe metadata is unavailable.
SECTOR_MAP: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "GOOGL": "Technology",
    "META": "Technology",
    "AMZN": "Consumer",
    "TSLA": "Consumer",
    "NFLX": "Communication",
    "JPM": "Financials",
    "XOM": "Energy",
    "CVX": "Energy",
    "UNH": "Health Care",
    "JNJ": "Health Care",
    "SPY": "Index",
    "QQQ": "Index",
    "IWM": "Index",
}


def _bias_from_events(events: list[NormalizedOptionsActivity]) -> float:
    if not events:
        return 0.0
    score = 0.0
    for e in events:
        _, direction = score_options_activity(e)
        if direction.value == "bullish":
            score += 1
        elif direction.value == "bearish":
            score -= 1
    return max(-1.0, min(1.0, score / len(events)))


def build_market_heatmap(
    universe: list[dict[str, Any]],
    *,
    size_by: str = "market_cap",
    color_by: str = "daily_return",
) -> dict[str, Any]:
    """
    universe items: symbol, sector, industry, market_cap, volume, dollar_volume,
                    daily_return, momentum_score, options_bias, exit_urgency
    """
    sectors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in universe:
        sector = row.get("sector") or SECTOR_MAP.get(str(row.get("symbol", "")).upper(), "Other")
        raw_color = row.get(color_by)
        if raw_color is None:
            raw_color = row.get("daily_return")
        color_value = float(raw_color if raw_color is not None else 0)
        size_raw = row.get(size_by)
        if size_raw is None:
            size_raw = row.get("market_cap")
        if size_raw is None:
            size_raw = row.get("volume")
        tile = {
            "symbol": row.get("symbol"),
            "sector": sector,
            "industry": row.get("industry") or "General",
            "size_value": float(size_raw if size_raw is not None else 1),
            "color_value": color_value,
            "daily_return": row.get("daily_return"),
            "momentum_score": row.get("momentum_score"),
            "options_bias": row.get("options_bias"),
            "exit_urgency": row.get("exit_urgency"),
            "label": _color_label(color_value, color_by),
        }
        # Drop null options_bias so equity heatmaps don't look like options bias maps.
        if tile["options_bias"] is None:
            tile.pop("options_bias", None)
        if tile["exit_urgency"] is None:
            tile.pop("exit_urgency", None)
        sectors[sector].append(tile)

    return {
        "size_by": size_by,
        "color_by": color_by,
        "sectors": [
            {
                "sector": sector,
                "tiles": sorted(tiles, key=lambda t: t["size_value"], reverse=True),
            }
            for sector, tiles in sorted(sectors.items())
        ],
        "legend": {
            "size": size_by,
            "color": color_by,
            "note": "Color encodes the selected metric; labels are color-independent.",
        },
        "table_fallback": [
            tile
            for sector_tiles in sectors.values()
            for tile in sector_tiles
        ],
    }


def build_options_bias_heatmap(events: list[NormalizedOptionsActivity]) -> dict[str, Any]:
    by_symbol: dict[str, list[NormalizedOptionsActivity]] = defaultdict(list)
    for e in events:
        by_symbol[e.underlying].append(e)

    universe = []
    for symbol, group in by_symbol.items():
        bias = _bias_from_events(group)
        prem = sum(float(x.estimated_premium or 0) for x in group)
        universe.append(
            {
                "symbol": symbol,
                "sector": group[0].sector or SECTOR_MAP.get(symbol, "Other"),
                "market_cap": prem or 1,
                "daily_return": bias * 2,  # scale for coloring only
                "options_bias": bias,
                "options_premium": prem,
                "data_status": group[0].data_status.value,
            }
        )
    payload = build_market_heatmap(universe, size_by="market_cap", color_by="options_bias")
    payload["color_by"] = "options_bias"
    payload["disclaimer"] = (
        "Options bias uses ask/bid aggressor heuristics and confirmation — not raw call/put volume alone."
    )
    return payload


def build_smart_money_heatmap(events: list[NormalizedOptionsActivity]) -> dict[str, Any]:
    by_symbol: dict[str, list[NormalizedOptionsActivity]] = defaultdict(list)
    for e in events:
        by_symbol[e.underlying].append(e)
    universe = []
    for symbol, group in by_symbol.items():
        prem = sum(float(x.estimated_premium or 0) for x in group)
        bias = _bias_from_events(group)
        universe.append(
            {
                "symbol": symbol,
                "sector": group[0].sector or SECTOR_MAP.get(symbol, "Other"),
                "market_cap": prem,
                "options_bias": bias,
                "daily_return": bias,
                "confidence": min(1.0, len(group) / 5),
                "why": (
                    f"{'Concentrated' if len(group) >= 2 else 'Large'} activity; "
                    f"bias={bias:+.2f}; may include hedges/spreads."
                ),
                "data_status": group[0].data_status.value,
                "provider": group[0].data_source,
            }
        )
    payload = build_market_heatmap(universe, size_by="market_cap", color_by="options_bias")
    payload["disclaimer"] = "Tile size = qualifying premium. Not institutional identity."
    return payload


def build_sector_rotation(events: list[NormalizedOptionsActivity], returns: dict[str, float] | None = None) -> list[dict[str, Any]]:
    returns = returns or {}
    by_sector: dict[str, list[NormalizedOptionsActivity]] = defaultdict(list)
    for e in events:
        sector = e.sector or SECTOR_MAP.get(e.underlying, "Other")
        by_sector[sector].append(e)

    rows = []
    for sector, group in by_sector.items():
        symbols = {e.underlying for e in group}
        rel = sum(returns.get(s, 0.0) for s in symbols) / max(len(symbols), 1)
        bias = _bias_from_events(group)
        classification, evidence = classify_sector(
            {
                "relative_return": rel,
                "breadth_above_ma": 0.55 + bias * 0.2,
                "acceleration": bias * 0.5,
                "options_bias": bias,
                "data_points": len(symbols),
            }
        )
        rows.append(
            {
                "sector": sector,
                "classification": classification.value,
                "relative_return": round(rel, 3),
                "options_bias": round(bias, 3),
                "member_count": len(symbols),
                "evidence": evidence,
            }
        )
    return sorted(rows, key=lambda r: r["relative_return"], reverse=True)


def _color_label(value: float, metric: str) -> str:
    if metric in ("exit_urgency",):
        if value >= 71:
            return "High urgency"
        if value >= 41:
            return "Elevated"
        return "Low urgency"
    if metric in ("daily_return",):
        if value >= 3:
            return "Strong up"
        if value >= 1:
            return "Up"
        if value >= 0.25:
            return "Slightly up"
        if value <= -3:
            return "Strong down"
        if value <= -1:
            return "Down"
        if value <= -0.25:
            return "Slightly down"
        return "Flat"
    if value > 0.5:
        return "Up / constructive"
    if value < -0.5:
        return "Down / pressured"
    return "Flat / mixed"
