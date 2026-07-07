"""Beginner-friendly trade timing, ITM odds, and strategy comparisons."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.engine.models import PlannedOpportunity


def _fmt_short(d: date) -> str:
    return d.strftime("%b %d")


def _fmt_long(d: date) -> str:
    return d.strftime("%a, %b %d")


def _move_needed_pct(option_type: str, strike: float, stock_price: float) -> float:
    if stock_price <= 0:
        return 0.0
    if option_type == "call":
        return max(0.0, (strike - stock_price) / stock_price * 100)
    return max(0.0, (stock_price - strike) / stock_price * 100)


def _is_itm(option_type: str, strike: float, stock_price: float) -> bool:
    if option_type == "call":
        return stock_price >= strike
    return stock_price <= strike


def _itm_status(probability: float) -> str:
    if probability >= 60:
        return "likely"
    if probability >= 40:
        return "building"
    return "unlikely"


def _itm_label(probability: float) -> str:
    if probability >= 60:
        return "Likely in the money"
    if probability >= 40:
        return "Building toward ITM"
    return "Unlikely ITM"


def _estimate_itm_probability(
    *,
    option_type: str,
    strike: float,
    stock_price: float,
    delta: float | None,
    days_ahead: int,
    days_to_expiration: int,
    trend_bullish: bool,
    profit_probability: float,
) -> float:
    """Estimate odds the option finishes in the money."""
    dte_left = days_to_expiration - days_ahead
    aligned = (option_type == "call" and trend_bullish) or (
        option_type == "put" and not trend_bullish
    )
    move_needed = _move_needed_pct(option_type, strike, stock_price)

    if dte_left <= 0:
        if _is_itm(option_type, strike, stock_price):
            base = min(92.0, profit_probability + 18)
        else:
            base = max(8.0, profit_probability - 22)
        return round(base, 1)

    delta_prob = abs(delta or 0.35) * 100
    trend_adj = 10 if aligned else -8
    move_penalty = min(18, move_needed * 2.5)
    decay = max(0.75, 1 - (days_ahead / max(days_to_expiration, 1)) * 0.35)

    prob = (delta_prob * decay) + trend_adj - move_penalty
    if dte_left <= 3:
        prob -= 6

    return round(min(90.0, max(10.0, prob)), 1)


def _purchase_window(
    *,
    days_to_expiration: int,
    profit_probability: float,
    trend_bullish: bool,
    option_type: str,
) -> dict[str, Any]:
    today = date.today()
    aligned = (option_type == "call" and trend_bullish) or (
        option_type == "put" and not trend_bullish
    )

    if days_to_expiration <= 5:
        start = today
        end = today + timedelta(days=1)
        reason = "Expiration is close — enter quickly or skip this trade."
    elif profit_probability >= 68 and aligned:
        start = today
        end = today + timedelta(days=2)
        reason = "Setup is strong now — buying early captures the move."
    elif profit_probability >= 55:
        start = today
        end = today + timedelta(days=3)
        reason = "Good setup — buy within the next few sessions on strength."
    else:
        start = today + timedelta(days=1)
        end = today + timedelta(days=4)
        reason = "Wait for a better entry; odds improve on a small pullback."

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "label": f"{_fmt_short(start)} – {_fmt_short(end)}",
        "friendly": f"Best time to buy: {_fmt_long(start)} to {_fmt_long(end)}",
        "reason": reason,
    }


def build_trade_plan(planned: PlannedOpportunity) -> dict[str, Any]:
    """Full beginner trade plan: timing, ITM path, and strategy menu."""
    candidate = planned.scored.candidate
    snapshot = planned.scored.scoring_snapshot or {}
    profit_probability = float(snapshot.get("profit_probability") or 50)
    stock_price = float(candidate.metadata.get("stock_price") or 0)
    strike = float(candidate.strike or 0)
    expiration = candidate.expiration or date.today()
    dte = candidate.days_to_expiration
    premium = float(candidate.premium or 0)

    move_needed = round(_move_needed_pct(candidate.option_type or "call", strike, stock_price), 1)
    breakeven = (
        round(strike + premium, 2)
        if candidate.option_type == "call"
        else round(strike - premium, 2)
    )

    purchase = _purchase_window(
        days_to_expiration=dte,
        profit_probability=profit_probability,
        trend_bullish=candidate.trend_bullish,
        option_type=candidate.option_type or "call",
    )

    milestone_offsets = sorted(
        {
            0,
            max(1, dte // 3),
            max(2, (2 * dte) // 3),
            dte,
        }
    )

    itm_timeline: list[dict[str, Any]] = []
    for offset in milestone_offsets:
        day = date.today() + timedelta(days=offset)
        if day > expiration:
            day = expiration
        prob = _estimate_itm_probability(
            option_type=candidate.option_type or "call",
            strike=strike,
            stock_price=stock_price,
            delta=candidate.delta,
            days_ahead=offset,
            days_to_expiration=dte,
            trend_bullish=candidate.trend_bullish,
            profit_probability=profit_probability,
        )
        if offset == 0:
            title = "If you buy now"
        elif offset >= dte:
            title = "At expiration"
        else:
            title = f"Day {offset}"

        itm_timeline.append(
            {
                "date": day.isoformat(),
                "label": _fmt_short(day),
                "title": title,
                "itm_probability_pct": prob,
                "status": _itm_status(prob),
                "status_label": _itm_label(prob),
            }
        )

    primary_name = (
        f"Buy {candidate.option_type.title()}" if candidate.option_type else "Buy Option"
    )
    spread_width = max(2.5, round(strike * 0.03, 0))
    spread_cost = round(premium * 0.55, 2)

    strategies: list[dict[str, Any]] = [
        {
            "id": f"long_{candidate.option_type}",
            "name": primary_name,
            "badge": "Best match",
            "difficulty": "Beginner",
            "rank": 1,
            "win_probability": profit_probability,
            "cost_per_contract": round(premium * 100, 0),
            "max_loss": f"${premium * 100:.0f}",
            "max_profit": "Unlimited if the stock moves strongly your way",
            "best_for": "You expect a clear move before expiration",
            "purchase_window": purchase["label"],
            "summary": (
                f"Pay ~${premium:.2f} per share (${premium * 100:.0f} per contract). "
                f"Stock must pass ${breakeven:.2f} by {_fmt_short(expiration)} to profit at expiry."
            ),
        },
        {
            "id": "debit_spread",
            "name": f"{candidate.option_type.title()} Debit Spread",
            "badge": "Lower cost",
            "difficulty": "Intermediate",
            "rank": 2,
            "win_probability": round(min(92, profit_probability + 12), 1),
            "cost_per_contract": round(spread_cost * 100, 0),
            "max_loss": f"${spread_cost * 100:.0f}",
            "max_profit": f"~${spread_width * 100:.0f} per contract (capped)",
            "best_for": "You want higher odds with less money at risk",
            "purchase_window": purchase["label"],
            "summary": (
                f"Buy your strike and sell a further {'higher' if candidate.option_type == 'call' else 'lower'} "
                f"strike. Costs less than a naked {candidate.option_type}, but profits are capped."
            ),
        },
        {
            "id": "stock_swing",
            "name": f"Buy {candidate.symbol} Shares",
            "badge": "Simplest",
            "difficulty": "Beginner",
            "rank": 3,
            "win_probability": round(min(88, profit_probability - 5), 1),
            "cost_per_contract": round(stock_price * 100, 0) if stock_price else None,
            "max_loss": "Full share price if stock collapses",
            "max_profit": "Unlimited — you own the stock",
            "best_for": "You want to avoid time decay and options complexity",
            "purchase_window": purchase["label"],
            "summary": (
                f"Skip the option and buy shares near ${stock_price:.2f}. "
                "No expiration date, but you need a larger account."
            ),
        },
    ]

    if profit_probability < 52:
        strategies.append(
            {
                "id": "watch_only",
                "name": "Watch — Don't Buy Yet",
                "badge": "Patience",
                "difficulty": "Beginner",
                "rank": 4,
                "win_probability": profit_probability,
                "cost_per_contract": 0,
                "max_loss": "$0",
                "max_profit": "Avoid a low-odds trade",
                "best_for": "The setup isn't strong enough right now",
                "purchase_window": "Wait",
                "summary": "Add to watchlist and re-scan when momentum or news improves.",
            }
        )

    strategies.sort(key=lambda s: (-s["win_probability"], s["rank"]))

    return {
        "expiration_date": expiration.isoformat(),
        "expiration_label": _fmt_long(expiration),
        "stock_price": stock_price,
        "breakeven_price": breakeven,
        "move_needed_pct": move_needed,
        "currently_itm": _is_itm(candidate.option_type or "call", strike, stock_price),
        "purchase_window": purchase,
        "itm_timeline": itm_timeline,
        "strategies": strategies,
        "recommended_strategy_id": strategies[0]["id"],
        "beginner_tip": (
            f"Start with the top strategy during {purchase['label']}. "
            f"The stock needs about a {move_needed:.1f}% move to reach your breakeven (${breakeven:.2f})."
        ),
    }
