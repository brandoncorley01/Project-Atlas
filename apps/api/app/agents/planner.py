from app.engine.models import PlannedOpportunity, ScoredOpportunity
from app.engine.strategy_guide import build_trade_plan


def plan_opportunity(scored: ScoredOpportunity) -> PlannedOpportunity:
    """Planner AI — entry, targets, hold time, and beginner trade plan."""
    candidate = scored.candidate
    premium = candidate.premium or 1.0

    entry_low = round(premium * 0.92, 2)
    entry_high = round(premium * 1.05, 2)
    targets = [round(premium * 1.35, 2), round(premium * 1.65, 2)]

    if candidate.days_to_expiration <= 5:
        hold = "1–3 days"
    elif candidate.days_to_expiration <= 14:
        hold = "3–7 days"
    else:
        hold = "1–2 weeks"

    planned = PlannedOpportunity(
        scored=scored,
        entry_zone={"low": entry_low, "high": entry_high},
        profit_targets=targets,
        max_loss=round(premium, 2),
        expected_hold_time=hold,
    )

    trade_plan = build_trade_plan(planned)
    scored.scoring_snapshot = {**(scored.scoring_snapshot or {}), "trade_plan": trade_plan}
    return planned
