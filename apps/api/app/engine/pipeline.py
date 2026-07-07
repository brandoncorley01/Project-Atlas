from datetime import date, timedelta

from app.agents.analyst import rank_scored, score_candidate
from app.agents.planner import plan_opportunity
from app.agents.scout import filter_candidates
from app.engine.explainer import explain_opportunity
from app.engine.models import CandidateOpportunity, ExplainedSignal, SignalModule
from app.engine.strategy_guide import build_trade_plan


def mock_options_candidates() -> list[CandidateOpportunity]:
    """Mock Scout feed — mix of pass/fail liquidity filters."""
    exp_short = date.today() + timedelta(days=7)
    exp_mid = date.today() + timedelta(days=14)

    return [
        CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="AAPL",
            option_type="call",
            strike=210.0,
            expiration=exp_mid,
            premium=3.45,
            bid=3.35,
            ask=3.45,
            volume=12500,
            open_interest=45000,
            delta=0.42,
            gamma=0.08,
            theta=-0.12,
            implied_volatility=28.5,
            relative_volume=1.8,
            has_catalyst=True,
            trend_bullish=True,
        ),
        CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="NVDA",
            option_type="call",
            strike=140.0,
            expiration=exp_short,
            premium=4.20,
            bid=4.05,
            ask=4.20,
            volume=22000,
            open_interest=62000,
            delta=0.38,
            gamma=0.09,
            theta=-0.18,
            implied_volatility=42.0,
            relative_volume=2.1,
            has_catalyst=False,
            trend_bullish=True,
        ),
        CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="TSLA",
            option_type="put",
            strike=175.0,
            expiration=exp_mid,
            premium=2.85,
            bid=2.75,
            ask=2.85,
            volume=8900,
            open_interest=31000,
            delta=-0.35,
            gamma=0.07,
            theta=-0.10,
            implied_volatility=38.0,
            relative_volume=1.4,
            has_catalyst=False,
            trend_bullish=False,
        ),
        # Filtered out — illiquid
        CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="ILLIQ",
            option_type="call",
            strike=10.0,
            expiration=exp_short,
            premium=0.15,
            bid=0.05,
            ask=0.20,
            volume=12,
            open_interest=80,
            delta=0.10,
            implied_volatility=55.0,
            relative_volume=0.5,
        ),
        # Filtered out — wide spread
        CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="WIDE",
            option_type="call",
            strike=50.0,
            expiration=exp_mid,
            premium=2.00,
            bid=1.00,
            ask=2.00,
            volume=500,
            open_interest=1200,
            delta=0.30,
            implied_volatility=30.0,
            relative_volume=1.0,
        ),
    ]


def run_options_pipeline(candidates: list[CandidateOpportunity] | None = None) -> list[ExplainedSignal]:
    """Full Opportunity Engine pipeline for options."""
    is_mock = candidates is None
    source = mock_options_candidates() if is_mock else candidates
    filtered = filter_candidates(source, strict=is_mock)
    scored = [score_candidate(c) for c in filtered]
    ranked = rank_scored(scored)
    explained: list[ExplainedSignal] = []

    for item in ranked:
        planned = plan_opportunity(item)
        explained.append(explain_opportunity(planned))

    return explained
