from app.engine.models import CandidateOpportunity, ScoredOpportunity


def _profit_probability_score(candidate: CandidateOpportunity) -> float:
    """Estimate directional win odds for a retail swing option."""
    prob = 48.0
    delta = abs(candidate.delta or 0.35)

    # Direction must match the underlying setup.
    if candidate.option_type == "call" and candidate.trend_bullish:
        prob += 14
    elif candidate.option_type == "put" and not candidate.trend_bullish:
        prob += 14
    else:
        prob -= 10

    # Sweet-spot delta: enough exposure without lottery-ticket odds.
    if 0.30 <= delta <= 0.50:
        prob += 12
    elif 0.22 <= delta < 0.30:
        prob += 4
    elif delta > 0.60:
        prob -= 6
    elif delta < 0.18:
        prob -= 8

    # Liquidity improves real fills and exit quality.
    if candidate.bid_ask_spread_pct <= 2.5:
        prob += 10
    elif candidate.bid_ask_spread_pct <= 5:
        prob += 5
    elif candidate.bid_ask_spread_pct > 8:
        prob -= 8

    if candidate.open_interest >= 2000:
        prob += 6
    elif candidate.open_interest >= 800:
        prob += 3

    if candidate.volume >= 200:
        prob += 5
    elif candidate.volume >= 75:
        prob += 2

    if candidate.has_catalyst:
        prob += 8

    dte = candidate.days_to_expiration
    if 5 <= dte <= 16:
        prob += 8
    elif dte <= 3:
        prob -= 12
    elif dte > 21:
        prob -= 4

    rsi = candidate.metadata.get("rsi")
    if rsi is not None:
        if candidate.option_type == "call" and 42 <= rsi <= 62:
            prob += 5
        elif candidate.option_type == "put" and 38 <= rsi <= 58:
            prob += 5
        elif candidate.option_type == "call" and rsi > 72:
            prob -= 6
        elif candidate.option_type == "put" and rsi < 28:
            prob -= 6

    rvol = candidate.relative_volume
    if rvol >= 1.4:
        prob += 5
    elif rvol < 0.7:
        prob -= 4

    return round(min(100.0, max(0.0, prob)), 2)


def score_candidate(candidate: CandidateOpportunity) -> ScoredOpportunity:
    """Analyst AI — deterministic weighted scoring."""
    technical = 0.0
    if candidate.trend_bullish:
        technical += 25
    technical += min(25, candidate.relative_volume * 8)

    catalyst = 20 if candidate.has_catalyst else 0
    impact = float(candidate.metadata.get("catalyst_impact") or 0)
    if impact >= 50:
        catalyst = min(38, catalyst + impact * 0.25)
    elif impact >= 35:
        catalyst = min(32, catalyst + impact * 0.15)
    data_quality = 15
    if candidate.bid_ask_spread_pct <= 3:
        data_quality += 10
    if candidate.open_interest >= 2000:
        data_quality += 5

    confidence = min(100.0, technical + catalyst + data_quality)

    spread_risk = min(40, candidate.bid_ask_spread_pct * 4)
    time_risk = 25 if candidate.days_to_expiration <= 3 else (10 if candidate.days_to_expiration <= 7 else 0)
    vol_risk = 15 if (candidate.implied_volatility or 0) > 45 else 5
    risk = min(100.0, spread_risk + time_risk + vol_risk)

    profit_probability = _profit_probability_score(candidate)
    ev_proxy = confidence * 0.45 + (100 - risk) * 0.35 + profit_probability * 0.20
    time_boost = 5 if candidate.has_catalyst and candidate.days_to_expiration <= 10 else 0
    opportunity = min(100.0, ev_proxy + time_boost)

    snapshot = {
        "technical": round(technical, 2),
        "catalyst": catalyst,
        "data_quality": data_quality,
        "spread_risk": round(spread_risk, 2),
        "time_risk": time_risk,
        "vol_risk": vol_risk,
        "ev_proxy": round(ev_proxy, 2),
        "profit_probability": profit_probability,
        "market_context": {
            "rsi": candidate.metadata.get("rsi"),
            "relative_volume": candidate.relative_volume,
            "has_catalyst": candidate.has_catalyst,
            "news_count": candidate.metadata.get("news_count"),
            "top_headline": candidate.metadata.get("top_headline"),
            "trend_bullish": candidate.trend_bullish,
            "delta": candidate.delta,
            "profit_probability": profit_probability,
            "discovery_sources": candidate.metadata.get("discovery_sources", []),
            "catalyst_impact": candidate.metadata.get("catalyst_impact"),
            "catalyst_sentiment": candidate.metadata.get("catalyst_sentiment"),
        },
    }

    return ScoredOpportunity(
        candidate=candidate,
        confidence_score=round(confidence, 2),
        risk_score=round(risk, 2),
        opportunity_score=round(opportunity, 2),
        scoring_snapshot=snapshot,
    )


def rank_scored(scored: list[ScoredOpportunity]) -> list[ScoredOpportunity]:
    """Rank by profit probability, with under-$100 contracts as a soft tie-break."""
    from app.agents.scout import is_budget_contract

    def sort_key(item: ScoredOpportunity) -> tuple[float, float, float, float]:
        snap = item.scoring_snapshot or {}
        prob = float(snap.get("profit_probability") or 0)
        budget = 1.0 if is_budget_contract(item.candidate) else 0.0
        return (prob, budget, item.opportunity_score, item.confidence_score)

    return sorted(scored, key=sort_key, reverse=True)
