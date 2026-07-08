"""Auto-grade stock and options picks when they expire."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.freshness import parse_iso


def stock_return_pct(entry: float, current: float, *, is_long: bool) -> float:
    if entry <= 0:
        return 0.0
    if is_long:
        return round((current - entry) / entry * 100, 2)
    return round((entry - current) / entry * 100, 2)


def _is_long_recommendation(rec: str) -> bool:
    r = rec.lower().strip()
    return r in ("buy", "long", "bullish", "accumulate", "hold")


def grade_stock_pick(signal: dict[str, Any], current_price: float) -> tuple[str, float] | None:
    """Grade an expired stock swing against live price."""
    if current_price <= 0:
        return None

    entry = signal.get("entry_range") or {}
    entry_low = float(entry.get("low") or 0)
    entry_high = float(entry.get("high") or 0)
    stop = float(signal.get("stop_loss") or 0)
    targets = signal.get("profit_targets") or []
    scan_price = float(signal.get("current_price") or 0)

    if entry_low > 0 and entry_high > 0:
        entry_mid = (entry_low + entry_high) / 2
    elif scan_price > 0:
        entry_mid = scan_price
    else:
        return None

    is_long = _is_long_recommendation(str(signal.get("recommendation") or "buy"))
    ret = stock_return_pct(entry_mid, current_price, is_long=is_long)

    if stop > 0:
        if is_long and current_price <= stop:
            return "loss", ret
        if not is_long and current_price >= stop:
            return "loss", ret

    if targets:
        first_target = float(targets[0])
        if is_long and current_price >= first_target:
            return "win", ret
        if not is_long and current_price <= first_target:
            return "win", ret

    if abs(ret) < 0.5:
        return "scratch", ret
    return ("win" if ret > 0 else "loss"), ret


def grade_options_pick(signal: dict[str, Any], spot_price: float) -> tuple[str, float] | None:
    """Grade an expired option contract against underlying spot."""
    exp = parse_iso(signal.get("expiration"))
    if not exp:
        return None
    now = datetime.now(UTC)
    if now.date() < exp.date():
        return None

    strike = float(signal.get("strike") or 0)
    premium = float(signal.get("premium") or 0)
    if strike <= 0 or premium <= 0:
        return None

    opt_type = str(signal.get("option_type") or "call").lower()
    if opt_type == "put":
        intrinsic = max(0.0, strike - spot_price)
    else:
        intrinsic = max(0.0, spot_price - strike)

    pnl_pct = round((intrinsic - premium) / premium * 100, 2)
    if intrinsic > premium * 1.05:
        return "win", pnl_pct
    if intrinsic <= 0.01:
        return "loss", -100.0
    if pnl_pct >= 0:
        return "win", pnl_pct
    return "loss", pnl_pct


def stock_ready_to_grade(signal: dict[str, Any]) -> bool:
    """True when stock signal is expired/stale enough to grade."""
    status = str(signal.get("status") or "")
    if status not in ("expired", "active"):
        return status == "closed"
    from app.services.freshness import is_stock_fresh

    return not is_stock_fresh(signal)


def options_ready_to_grade(signal: dict[str, Any]) -> bool:
    exp = parse_iso(signal.get("expiration"))
    if not exp:
        return False
    return datetime.now(UTC).date() >= exp.date()
