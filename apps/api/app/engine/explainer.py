from app.engine.models import ExplainedSignal, PlannedOpportunity


def explain_opportunity(planned: PlannedOpportunity) -> ExplainedSignal:
    """Generate structured explanation from facts — no LLM required for M2."""
    c = planned.scored.candidate
    s = planned.scored
    direction = "bullish" if c.option_type == "call" else "bearish"
    rsi = c.metadata.get("rsi")
    rsi_note = f" RSI {rsi:.0f}." if rsi is not None else ""

    recommendation = (
        f"{direction.capitalize()} {c.option_type} swing on {c.symbol} — "
        f"~{s.scoring_snapshot.get('profit_probability', 0):.0f}% profit probability, "
        f"opportunity score {s.opportunity_score:.0f}."
    )

    explanation = (
        f"{c.symbol} ${c.strike:.0f} {c.option_type} shows {direction} technical alignment "
        f"with relative volume {c.relative_volume:.1f}x, spread {c.bid_ask_spread_pct:.1f}%, "
        f"and {c.days_to_expiration} DTE.{rsi_note} "
        f"Confidence {s.confidence_score:.0f}, risk {s.risk_score:.0f}."
    )

    if c.has_catalyst and c.metadata.get("top_headline"):
        bull_case = (
            f"News catalyst: {c.metadata['top_headline']} "
            f"Trend and volume support a {direction} move."
        )
    else:
        bull_case = (
            f"Trend and volume support a {direction} move. "
            f"Open interest ({c.open_interest:,}) and volume ({c.volume:,}) suggest institutional interest."
        )

    bear_case = (
        f"Time decay (theta) erodes premium quickly with {c.days_to_expiration} DTE. "
        f"IV at {c.implied_volatility or 0:.0f}% may compress if volatility drops."
    )

    invalidation = (
        f"Setup invalid if {c.symbol} breaks key support/resistance against the {c.option_type} thesis "
        f"or spread widens beyond 8%."
    )

    suggested_action = (
        f"Consider entry between ${planned.entry_zone['low']:.2f}–${planned.entry_zone['high']:.2f}. "
        f"Target ${planned.profit_targets[0]:.2f} / ${planned.profit_targets[1]:.2f}. "
        f"Max loss ~${planned.max_loss:.2f} (premium paid)."
    )

    return ExplainedSignal(
        planned=planned,
        recommendation=recommendation,
        explanation=explanation,
        bull_case=bull_case,
        bear_case=bear_case,
        invalidation=invalidation,
        suggested_action=suggested_action,
    )
