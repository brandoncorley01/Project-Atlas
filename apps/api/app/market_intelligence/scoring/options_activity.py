"""Unusual options activity scoring (explainable, versioned)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.market_intelligence.scoring.versions import OPTIONS_ACTIVITY_V1, OPTIONS_ACTIVITY_WEIGHTS
from app.market_intelligence.types import (
    DirectionLabel,
    NormalizedOptionsActivity,
    ScoreBreakdown,
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _spread_pct(event: NormalizedOptionsActivity) -> float | None:
    if event.bid is None or event.ask is None or event.midpoint is None or event.midpoint <= 0:
        return None
    return float((event.ask - event.bid) / event.midpoint * Decimal("100"))


def _moneyness(event: NormalizedOptionsActivity) -> float | None:
    if event.underlying_price is None or event.underlying_price <= 0:
        return None
    return float(event.strike / event.underlying_price)


def classify_direction(event: NormalizedOptionsActivity, components: dict[str, float]) -> DirectionLabel:
    """Calls are not always bullish; puts are not always bearish."""
    side = (event.execution_class or "unknown").lower()
    flow = (event.flow_class or "unknown").lower()
    open_close = (event.open_close or "unknown").lower()

    if open_close == "closing":
        return DirectionLabel.UNCERTAIN
    if flow in ("spread",) or "spread" in str(event.raw_metadata.get("notes", "")).lower():
        return DirectionLabel.POSSIBLE_SPREAD
    if event.contracts and event.contracts >= 500 and side == "mid":
        return DirectionLabel.POSSIBLE_HEDGE

    if event.option_type == "call":
        if side == "ask":
            return DirectionLabel.BULLISH
        if side == "bid":
            return DirectionLabel.BEARISH  # call selling aggressor
        return DirectionLabel.UNCERTAIN
    if event.option_type == "put":
        if side == "ask":
            return DirectionLabel.BEARISH
        if side == "bid":
            return DirectionLabel.BULLISH  # put selling aggressor
        return DirectionLabel.UNCERTAIN
    return DirectionLabel.UNCERTAIN


def score_options_activity(
    event: NormalizedOptionsActivity,
    *,
    repeat_count: int = 1,
    underlying_momentum: float | None = None,
    has_news_catalyst: bool | None = None,
    regime_support: float | None = None,
    now: datetime | None = None,
) -> tuple[ScoreBreakdown, DirectionLabel]:
    """Return OptionsActivityScore 0–100 with component transparency."""
    now = now or datetime.now(UTC)
    components: dict[str, float] = {}
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []
    penalties: list[str] = []

    # Volume / OI
    if event.volume_oi_ratio is not None:
        voi = float(event.volume_oi_ratio)
        components["volume_oi"] = _clamp(min(voi, 5.0) / 5.0 * 100)
        if voi >= 1.0:
            positives.append(f"Volume/OI {voi:.2f} elevated")
        elif voi < 0.2:
            negatives.append(f"Volume/OI {voi:.2f} weak")
    else:
        missing.append("volume_oi_ratio")
        components["volume_oi"] = 35.0
        penalties.append("Missing volume/OI (−)")

    # Premium size
    if event.estimated_premium is not None:
        prem = float(event.estimated_premium)
        # Log-ish scale: $50k → ~50, $500k → ~85
        components["premium"] = _clamp(20 + (prem / 10000) ** 0.5 * 12)
        if prem >= 100_000:
            positives.append(f"Notional ~${prem:,.0f}")
        elif prem < 5_000:
            negatives.append("Small premium notional")
    else:
        missing.append("estimated_premium")
        components["premium"] = 30.0
        penalties.append("Missing premium (−)")

    # Spread quality (tight = higher)
    spread = _spread_pct(event)
    if spread is not None:
        if spread <= 5:
            components["spread"] = 90.0
            positives.append(f"Tight spread {spread:.1f}%")
        elif spread <= 12:
            components["spread"] = 65.0
        elif spread <= 25:
            components["spread"] = 35.0
            negatives.append(f"Wide spread {spread:.1f}%")
        else:
            components["spread"] = 10.0
            negatives.append(f"Extremely wide spread {spread:.1f}%")
            penalties.append("Illiquid quote")
    else:
        missing.append("bid_ask")
        components["spread"] = 25.0
        penalties.append("Missing bid/ask (−)")

    # Flow class
    flow = (event.flow_class or "unknown").lower()
    flow_map = {"sweep": 88.0, "block": 80.0, "split": 60.0, "standard": 45.0, "unknown": 40.0}
    components["flow_class"] = flow_map.get(flow, 40.0)
    if flow in ("sweep", "block"):
        positives.append(f"{flow.title()} classification")
    elif flow == "unknown":
        missing.append("flow_class")

    # Repeat similar orders
    components["repeat"] = _clamp(30 + (repeat_count - 1) * 18)
    if repeat_count >= 3:
        positives.append(f"Repeated similar activity ×{repeat_count}")
    elif repeat_count <= 1:
        negatives.append("Single isolated print")

    # Delta / moneyness
    if event.delta is not None:
        d = abs(float(event.delta))
        components["delta"] = _clamp(d * 100)
        if d < 0.15:
            negatives.append("Deep OTM / lottery-like delta")
            penalties.append("Extreme OTM delta")
        elif 0.25 <= d <= 0.55:
            positives.append(f"Usable delta {d:.2f}")
    else:
        m = _moneyness(event)
        if m is None:
            missing.append("delta")
            components["delta"] = 40.0
        else:
            # Prefer near-the-money
            dist = abs(m - 1.0)
            components["delta"] = _clamp(100 - dist * 200)
            if dist > 0.2:
                negatives.append("Far from the money")
                penalties.append("Extreme OTM moneyness")

    # Underlying momentum (optional confirmation)
    if underlying_momentum is None:
        missing.append("underlying_momentum")
        components["momentum"] = 45.0
    else:
        components["momentum"] = _clamp(50 + underlying_momentum * 8)
        if underlying_momentum > 1:
            positives.append("Supporting price momentum")
        elif underlying_momentum < -1:
            negatives.append("Opposing price momentum")

    # News
    if has_news_catalyst is None:
        missing.append("news_catalyst")
        components["news"] = 40.0
    else:
        components["news"] = 75.0 if has_news_catalyst else 35.0
        if has_news_catalyst:
            positives.append("Supporting catalyst present")

    # Regime
    if regime_support is None:
        missing.append("market_regime")
        components["regime"] = 45.0
    else:
        components["regime"] = _clamp(50 + regime_support * 25)
        if regime_support > 0.2:
            positives.append("Market regime supportive")
        elif regime_support < -0.2:
            negatives.append("Market regime headwind")

    # Weighted score
    total = 0.0
    for key, weight in OPTIONS_ACTIVITY_WEIGHTS.items():
        total += components.get(key, 40.0) * weight

    # Hard penalties
    oi = event.open_interest
    vol = event.contract_volume
    oi_unknown = oi is None or int(oi) == 0
    if oi_unknown:
        # Do not treat Yahoo's missing OI as near-zero liquidity when volume is strong
        if vol is not None and int(vol) < 50:
            total -= 15
            penalties.append("Open interest unknown and volume very low")
    elif int(oi) < 50:
        total -= 15
        penalties.append("Near-zero open interest")
    if event.contract_volume is not None and event.contract_volume < 20:
        total -= 10
        penalties.append("Very low volume")
    if spread is not None and spread > 30:
        total -= 20
        penalties.append("Untradeable spread")

    final = _clamp(total)
    missing_ratio = len(missing) / max(len(OPTIONS_ACTIVITY_WEIGHTS), 1)
    confidence = _clamp(88 - missing_ratio * 55 - len(penalties) * 4)
    if len(missing) <= 1 and not penalties:
        quality = "high"
    elif len(missing) <= 3:
        quality = "medium"
    else:
        quality = "low"

    direction = classify_direction(event, components)
    if direction in (DirectionLabel.UNCERTAIN, DirectionLabel.POSSIBLE_HEDGE, DirectionLabel.POSSIBLE_SPREAD):
        confidence = min(confidence, 55.0)
        negatives.append(f"Intent labeled {direction.value}")

    breakdown = ScoreBreakdown(
        score_key="options_activity",
        score_version=OPTIONS_ACTIVITY_V1,
        final_score=final,
        confidence=confidence,
        data_quality=quality,
        component_values=components,
        weights=dict(OPTIONS_ACTIVITY_WEIGHTS),
        positive_contributors=positives,
        negative_contributors=negatives,
        missing_inputs=missing,
        penalties=penalties,
        evaluation_timestamp=now,
        data_timestamp=event.data_timestamp,
        data_freshness=event.data_status.value,
    )
    return breakdown, direction
