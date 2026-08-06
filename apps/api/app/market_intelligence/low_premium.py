"""Low-premium opportunity scanner — cheap ≠ high rank."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.market_intelligence.scoring.options_activity import score_options_activity
from app.market_intelligence.types import NormalizedOptionsActivity


@dataclass
class LowPremiumFilters:
    max_contract_price: float = 5.0
    max_position_risk: float = 500.0  # 1 contract * 100 * price
    option_type: str | None = None  # call | put | None
    min_dte: int = 7
    max_dte: int = 45
    min_open_interest: int = 200
    min_volume: int = 100
    max_spread_pct: float = 12.0
    min_unusual_score: float = 55.0
    min_confidence: float = 45.0
    min_delta: float | None = 0.20
    max_otm_pct: float = 0.12
    require_catalyst: bool = False


def _spread_pct(event: NormalizedOptionsActivity) -> float | None:
    if event.bid is None or event.ask is None or not event.midpoint or event.midpoint <= 0:
        return None
    return float((event.ask - event.bid) / event.midpoint * Decimal(100))


def _dte(event: NormalizedOptionsActivity, as_of_date) -> int | None:
    try:
        return (event.expiration - as_of_date).days
    except Exception:
        return None


def scan_low_premium(
    events: list[NormalizedOptionsActivity],
    *,
    filters: LowPremiumFilters | None = None,
    as_of=None,
    repeat_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or LowPremiumFilters()
    from datetime import date as date_cls

    as_of = as_of or date_cls.today()
    repeats = repeat_counts or {}
    results: list[dict[str, Any]] = []

    for event in events:
        rejects: list[str] = []
        price = float(event.contract_price or event.midpoint or 0)
        if price <= 0 or price > filters.max_contract_price:
            rejects.append("price_out_of_range")
        risk = price * 100
        if risk > filters.max_position_risk:
            rejects.append("position_risk_too_high")
        if filters.option_type and event.option_type != filters.option_type:
            rejects.append("option_type")
        dte = _dte(event, as_of)
        if dte is None:
            rejects.append("missing_dte")
        elif dte < filters.min_dte:
            rejects.append("expires_too_soon")
        elif dte > filters.max_dte:
            rejects.append("expires_too_far")
        oi = event.open_interest
        vol = event.contract_volume or 0
        oi_unknown = oi is None or int(oi) == 0
        if oi_unknown:
            # Yahoo often reports OI=0 — require stronger volume instead of hard reject
            if vol < max(filters.min_volume, 250):
                rejects.append("open_interest")
        elif int(oi) < filters.min_open_interest:
            rejects.append("open_interest")
        if vol < filters.min_volume:
            rejects.append("volume")
        spread = _spread_pct(event)
        if spread is None:
            rejects.append("missing_spread")
        elif spread > filters.max_spread_pct:
            rejects.append("spread_too_wide")
        if filters.min_delta is not None:
            if event.delta is None:
                rejects.append("missing_delta")
            elif abs(float(event.delta)) < filters.min_delta:
                rejects.append("delta_too_low")
        if event.underlying_price and event.underlying_price > 0:
            otm = abs(float(event.strike / event.underlying_price) - 1.0)
            if otm > filters.max_otm_pct:
                rejects.append("too_far_otm")

        key = f"{event.underlying}:{event.option_type}"
        breakdown, direction = score_options_activity(
            event,
            repeat_count=repeats.get(key, 1),
        )
        if breakdown.final_score < filters.min_unusual_score:
            rejects.append("unusual_score")
        if breakdown.confidence < filters.min_confidence:
            rejects.append("confidence")
        if filters.require_catalyst and "news_catalyst" in breakdown.missing_inputs:
            rejects.append("catalyst_required")

        # Cheapness alone must not rank highly — rank by score, not inverse price
        rank_score = breakdown.final_score * 0.7 + breakdown.confidence * 0.3
        if "spread_too_wide" in rejects or "open_interest" in rejects or "too_far_otm" in rejects:
            continue  # hard reject

        if rejects:
            continue

        results.append(
            {
                "event": event.to_dict(),
                "direction": direction.value,
                "score": breakdown.to_dict(),
                "rank_score": round(rank_score, 2),
                "position_risk": round(risk, 2),
                "spread_pct": spread,
                "dte": dte,
                "review_zone": {
                    "note": "Suggested review zone — not a guaranteed entry",
                    "premium_ref": str(event.midpoint or event.contract_price),
                },
            }
        )

    results.sort(key=lambda r: r["rank_score"], reverse=True)
    return results
