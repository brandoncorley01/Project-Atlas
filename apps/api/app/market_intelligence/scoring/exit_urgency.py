"""Swing-trade exit urgency scoring (decision support only)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.market_intelligence.scoring.versions import EXIT_V1, EXIT_WEIGHTS
from app.market_intelligence.types import ExitAction, ScoreBreakdown


EXIT_LABELS = [
    (20, "Strong Hold"),
    (40, "Hold"),
    (55, "Monitor Closely"),
    (70, "Tighten Risk"),
    (85, "Scale Out"),
    (100, "Exit Review"),
]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def urgency_label(score: float) -> str:
    for ceiling, label in EXIT_LABELS:
        if score <= ceiling:
            return label
    return "Exit Review"


def action_from_score(
    score: float,
    *,
    thesis_invalid: bool,
    insufficient: bool,
    at_target: bool,
) -> ExitAction:
    if insufficient:
        return ExitAction.INSUFFICIENT_DATA
    if thesis_invalid:
        return ExitAction.THESIS_INVALIDATED
    if score >= 86:
        return ExitAction.EXIT_REVIEW
    if score >= 71:
        return ExitAction.SCALE_OUT if at_target else ExitAction.TAKE_PARTIAL
    if score >= 56:
        return ExitAction.TIGHTEN_STOP
    if score >= 41:
        return ExitAction.HOLD_TRAILING
    if score <= 20 and at_target is False:
        return ExitAction.HOLD
    return ExitAction.HOLD


def score_exit_urgency(context: dict[str, Any], *, now: datetime | None = None) -> tuple[ScoreBreakdown, ExitAction, str]:
    """
    context keys (all optional; missing lowers confidence):
      return_pct, momentum_score (-1..1), trend_ok (bool), relative_volume,
      options_support (-1..1), sector_support (-1..1), market_support (-1..1),
      thesis_valid (bool), reward_risk (float), days_to_event, iv_crush (bool),
      at_first_target (bool), time_in_trade_days
    """
    now = now or datetime.now(UTC)
    components: dict[str, float] = {}
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []
    penalties: list[str] = []

    # Higher component = higher exit urgency
    mom = context.get("momentum_score")
    if mom is None:
        missing.append("momentum_score")
        components["momentum"] = 45.0
    else:
        # Deteriorating momentum raises urgency
        components["momentum"] = _clamp(50 - float(mom) * 35)
        if float(mom) < -0.3:
            negatives.append("Momentum deteriorating")
        elif float(mom) > 0.3:
            positives.append("Momentum still constructive")

    trend_ok = context.get("trend_ok")
    if trend_ok is None:
        missing.append("trend_ok")
        components["trend"] = 45.0
    else:
        components["trend"] = 25.0 if trend_ok else 80.0
        if not trend_ok:
            negatives.append("Primary trend level broken")
        else:
            positives.append("Still above primary trend level")

    rvol = context.get("relative_volume")
    if rvol is None:
        missing.append("relative_volume")
        components["volume"] = 40.0
    else:
        # Exhaustion / reversal volume near highs elevates urgency when return positive
        components["volume"] = _clamp(30 + float(rvol) * 15)
        if float(rvol) > 2 and float(context.get("return_pct") or 0) > 5:
            negatives.append("Elevated volume after strong run")

    opt = context.get("options_support")
    if opt is None:
        missing.append("options_support")
        components["options"] = 45.0
    else:
        components["options"] = _clamp(50 - float(opt) * 40)
        if float(opt) < -0.2:
            negatives.append("Options flow turning against position")
        elif float(opt) > 0.2:
            positives.append("Options flow still supportive")

    sector = context.get("sector_support")
    if sector is None:
        missing.append("sector_support")
        components["sector"] = 45.0
    else:
        components["sector"] = _clamp(50 - float(sector) * 40)
        if float(sector) < -0.2:
            negatives.append("Sector weakening")
        elif float(sector) > 0.2:
            positives.append("Sector still leading")

    market = context.get("market_support")
    if market is None:
        missing.append("market_support")
        components["market"] = 45.0
    else:
        components["market"] = _clamp(50 - float(market) * 40)
        if float(market) < -0.2:
            negatives.append("Market regime headwind")

    thesis = context.get("thesis_valid")
    if thesis is None:
        missing.append("thesis_valid")
        components["thesis"] = 50.0
    else:
        components["thesis"] = 20.0 if thesis else 95.0
        if not thesis:
            negatives.append("Original thesis no longer valid")
            penalties.append("Thesis invalidation")
        else:
            positives.append("Original thesis remains intact")

    rr = context.get("reward_risk")
    if rr is None:
        missing.append("reward_risk")
        components["reward_risk"] = 45.0
    else:
        # Low remaining R:R → higher urgency
        components["reward_risk"] = _clamp(80 - float(rr) * 25)
        if float(rr) < 1:
            negatives.append("Remaining reward-to-risk compressed")

    dte_event = context.get("days_to_event")
    if dte_event is None:
        missing.append("days_to_event")
        components["event"] = 35.0
    else:
        if float(dte_event) <= 2:
            components["event"] = 75.0
            negatives.append("Event risk imminent")
        elif context.get("iv_crush"):
            components["event"] = 70.0
            negatives.append("IV crush / catalyst completed")
            penalties.append("Catalyst completion")
        else:
            components["event"] = 30.0

    total = 0.0
    for key, weight in EXIT_WEIGHTS.items():
        total += components.get(key, 45.0) * weight

    final = _clamp(total)
    missing_ratio = len(missing) / max(len(EXIT_WEIGHTS), 1)
    confidence = _clamp(90 - missing_ratio * 50 - len(penalties) * 5)
    quality = "high" if len(missing) <= 2 else ("medium" if len(missing) <= 5 else "low")
    insufficient = quality == "low" and confidence < 40
    thesis_invalid = thesis is False
    at_target = bool(context.get("at_first_target"))

    action = action_from_score(
        final,
        thesis_invalid=thesis_invalid,
        insufficient=insufficient,
        at_target=at_target,
    )
    label = urgency_label(final)

    explanation = _build_explanation(action, positives, negatives, label)

    breakdown = ScoreBreakdown(
        score_key="exit_urgency",
        score_version=EXIT_V1,
        final_score=final,
        confidence=confidence,
        data_quality=quality,
        component_values=components,
        weights=dict(EXIT_WEIGHTS),
        positive_contributors=positives,
        negative_contributors=negatives,
        missing_inputs=missing,
        penalties=penalties,
        evaluation_timestamp=now,
        data_timestamp=now,
        data_freshness="evaluated",
    )
    return breakdown, action, explanation


def _build_explanation(
    action: ExitAction,
    positives: list[str],
    negatives: list[str],
    label: str,
) -> str:
    pos = "; ".join(positives[:2]) if positives else "limited constructive evidence"
    neg = "; ".join(negatives[:2]) if negatives else "no major deterioration flagged"
    return (
        f"{action.value}. Urgency band: {label}. "
        f"Supporting: {pos}. Watch: {neg}. "
        "This is decision support, not an order instruction."
    )
