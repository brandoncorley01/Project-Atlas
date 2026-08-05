"""Expected move and IV-crush estimates for earnings setups."""

from __future__ import annotations

import math
from typing import Any


def historical_avg_move(moves: list[float] | None) -> float | None:
    vals = [abs(float(m)) for m in (moves or []) if m is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def expected_move_from_iv(
    *,
    price: float,
    iv: float | None,
    days_to_event: float = 1.0,
) -> float | None:
    """
    Approximate 1-sigma move from IV.
    `iv` may be percent (28) or decimal (0.28).
    Returns percent of spot.
    """
    if price <= 0 or iv is None:
        return None
    iv_dec = float(iv)
    if iv_dec > 3:  # clearly a percent
        iv_dec = iv_dec / 100.0
    if iv_dec <= 0:
        return None
    t = max(float(days_to_event), 0.25) / 365.0
    move = price * iv_dec * math.sqrt(t)
    return round((move / price) * 100.0, 2)


def expected_move_from_straddle(
    *,
    price: float,
    call_mid: float | None,
    put_mid: float | None,
) -> float | None:
    """ATM straddle mid / spot as expected-move percent."""
    if price <= 0:
        return None
    if call_mid is None or put_mid is None:
        return None
    if call_mid <= 0 or put_mid <= 0:
        return None
    return round(((call_mid + put_mid) / price) * 100.0, 2)


def blend_expected_move(
    *,
    straddle_pct: float | None,
    iv_pct: float | None,
    historical_pct: float | None,
) -> dict[str, Any]:
    """Prefer straddle, then IV, then historical — never invent a number."""
    sources: list[tuple[str, float]] = []
    if straddle_pct is not None and straddle_pct > 0:
        sources.append(("atm_straddle", float(straddle_pct)))
    if iv_pct is not None and iv_pct > 0:
        sources.append(("iv_sigma", float(iv_pct)))
    if historical_pct is not None and historical_pct > 0:
        sources.append(("historical_avg", float(historical_pct)))
    if not sources:
        return {"expected_move_pct": None, "source": None, "inputs": {}}
    # Weighted blend when multiple available
    if len(sources) == 1:
        return {
            "expected_move_pct": round(sources[0][1], 2),
            "source": sources[0][0],
            "inputs": {k: v for k, v in sources},
        }
    weights = {"atm_straddle": 0.5, "iv_sigma": 0.3, "historical_avg": 0.2}
    num = sum(v * weights.get(k, 0.2) for k, v in sources)
    den = sum(weights.get(k, 0.2) for k, _ in sources)
    return {
        "expected_move_pct": round(num / den, 2),
        "source": "blended",
        "inputs": {k: v for k, v in sources},
    }


def estimate_iv_crush_pct(
    *,
    pre_iv: float | None,
    historical_crush: float | None = None,
) -> float | None:
    """
    Rough post-earnings IV crush estimate.
    Prefer historical crush when provided; else apply a conservative 25–40% band
    scaled by elevated pre-IV. Returns percent reduction (e.g. 31 = 31% crush).
    """
    if historical_crush is not None and historical_crush > 0:
        return round(float(historical_crush), 1)
    if pre_iv is None:
        return None
    iv = float(pre_iv)
    if iv > 3:
        iv = iv / 100.0
    # Elevated IV → larger expected crush, capped
    base = 0.28
    if iv >= 0.8:
        base = 0.38
    elif iv >= 0.5:
        base = 0.33
    elif iv >= 0.35:
        base = 0.30
    return round(base * 100.0, 1)
