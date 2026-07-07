"""Lightweight greek estimates when the data provider omits them."""

from __future__ import annotations


def estimate_delta(option_type: str, strike: float, stock_price: float) -> float:
    """Rough ATM delta proxy from moneyness — good enough for retail swing ranking."""
    if stock_price <= 0 or strike <= 0:
        return 0.35

    moneyness = (stock_price - strike) / stock_price
    if option_type == "call":
        return round(max(0.12, min(0.78, 0.42 + moneyness * 2.8)), 3)
    return round(max(0.12, min(0.78, 0.42 - moneyness * 2.8)), 3)
