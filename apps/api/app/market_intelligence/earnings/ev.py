"""Expected-value and liquidity gates for earnings option strategies (paper-only)."""

from __future__ import annotations

from typing import Any


def spread_pct(bid: float | None, ask: float | None, mid: float | None = None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    m = mid if mid and mid > 0 else (bid + ask) / 2.0
    if m <= 0:
        return None
    return round(((ask - bid) / m) * 100.0, 2)


def liquidity_ok(
    *,
    volume: int | None,
    open_interest: int | None,
    spread: float | None,
    min_volume: int = 100,
    min_oi: int = 200,
    max_spread_pct: float = 12.0,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if volume is None or volume < min_volume:
        reasons.append(f"volume {volume} below {min_volume}")
    if open_interest is None or open_interest < min_oi:
        reasons.append(f"open interest {open_interest} below {min_oi}")
    if spread is None:
        reasons.append("bid-ask spread unavailable")
    elif spread > max_spread_pct:
        reasons.append(f"spread {spread}% above {max_spread_pct}%")
    return (len(reasons) == 0, reasons)


def breakeven_pct_for_call(*, premium: float, strike: float, spot: float) -> float | None:
    if spot <= 0 or premium < 0 or strike <= 0:
        return None
    return round(((strike + premium) / spot - 1.0) * 100.0, 2)


def breakeven_pct_for_put(*, premium: float, strike: float, spot: float) -> float | None:
    if spot <= 0 or premium < 0 or strike <= 0:
        return None
    return round((1.0 - (strike - premium) / spot) * 100.0, 2)


def reachable_breakeven(
    *,
    breakeven_pct: float | None,
    expected_move_pct: float | None,
    historical_avg_pct: float | None,
    modeled_range_pct: float | None = None,
) -> tuple[bool, str]:
    """Breakeven must sit inside a realistic move envelope — not just a huge % return dream."""
    if breakeven_pct is None:
        return False, "breakeven unavailable"
    envelope = None
    parts = [v for v in (expected_move_pct, historical_avg_pct, modeled_range_pct) if v is not None]
    if parts:
        envelope = max(parts) * 1.05  # small buffer
    if envelope is None:
        return False, "no expected/historical move envelope"
    if abs(breakeven_pct) > envelope:
        return False, f"breakeven {breakeven_pct}% beyond move envelope {envelope:.1f}%"
    return True, f"breakeven {breakeven_pct}% within envelope {envelope:.1f}%"


def expected_value(
    *,
    probability_of_profit: float,
    avg_gain: float,
    avg_loss: float,
    estimated_costs: float,
) -> float:
    """
    EV = p * gain - (1-p) * loss - costs
    Inputs in dollar (or consistent) units. probability in 0..1.
    """
    p = max(0.0, min(1.0, float(probability_of_profit)))
    return round(p * float(avg_gain) - (1.0 - p) * float(avg_loss) - float(estimated_costs), 4)


def estimate_trade_costs(
    *,
    premium: float,
    spread_pct_val: float | None,
    contracts: int = 1,
    slippage_pct: float = 1.5,
) -> float:
    """Rough round-trip cost in dollars for `contracts` (×100 multiplier)."""
    mid = max(float(premium), 0.01)
    spr = (spread_pct_val or 8.0) / 100.0
    per_share = mid * (spr / 2.0 + slippage_pct / 100.0)
    return round(per_share * 100.0 * max(contracts, 1) * 2.0, 2)  # round trip


def otm_passes_gates(checks: dict[str, Any]) -> tuple[bool, list[str]]:
    """Aggregate OTM qualification — large theoretical % return cannot override failures."""
    fails: list[str] = []
    if not checks.get("liquidity_ok"):
        fails.append("liquidity")
    if not checks.get("breakeven_reachable"):
        fails.append("breakeven")
    if not checks.get("positive_ev"):
        fails.append("expected_value")
    if not checks.get("max_loss_defined"):
        fails.append("max_loss")
    if not checks.get("within_risk_limit"):
        fails.append("risk_limit")
    return (len(fails) == 0, fails)


def micro_coattail_size(
    *,
    normal_paper_risk_usd: float,
    fraction: float,
    max_loss_per_contract: float | None,
) -> dict[str, Any]:
    """Configurable small fraction of normal paper risk. Always paper-only."""
    frac = max(0.01, min(0.5, float(fraction)))
    budget = round(float(normal_paper_risk_usd) * frac, 2)
    contracts = 1
    if max_loss_per_contract and max_loss_per_contract > 0:
        contracts = max(1, int(budget // max_loss_per_contract))
        if contracts < 1:
            contracts = 1
        # If even 1 contract exceeds budget, still allow 1 but flag oversized
    return {
        "paper_position_size_usd": budget,
        "contracts": contracts,
        "fraction": frac,
        "paper_only": True,
        "live_trading_enabled": False,
    }
