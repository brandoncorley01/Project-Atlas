"""Assemble Earnings Intelligence desk payloads (fixture-first, paper-only)."""

from __future__ import annotations

import logging
from typing import Any

from app.market_intelligence.earnings.engine import evaluate_earnings_setup
from app.market_intelligence.earnings.fixture_data import (
    FIXTURE_CHAINS,
    FIXTURE_EVENTS,
    fixture_watchlist,
)
from app.market_intelligence.earnings.types import EarningsPhase, EarningsRecType
from app.market_intelligence.freshness import build_freshness, utcnow
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)


def build_earnings_desk(
    *,
    normal_paper_risk_usd: float = 100.0,
    micro_fraction: float = 0.18,
    allow_simulated: bool = True,
) -> dict[str, Any]:
    """
    Full desk: upcoming, watchlist, pre/post opportunities, micro-coattails, recently reviewed.
    Always paper_only=True. Uses deterministic fixtures (Yahoo enrichment can replace later).
    """
    if not allow_simulated:
        return {
            "upcoming": [],
            "watchlist": [],
            "pre_earnings": [],
            "post_earnings": [],
            "micro_coattails": [],
            "recently_reviewed": [],
            "paper_only": True,
            "live_trading_enabled": False,
            "freshness": build_freshness(
                provider_name="Earnings Intelligence",
                data_timestamp=None,
                data_status=DataStatus.PARTIAL,
                missing_fields=["earnings_provider"],
            ).to_dict(),
            "disclaimer": "Simulated earnings fixtures disabled.",
        }

    recommendations = []
    for event in FIXTURE_EVENTS:
        chain = FIXTURE_CHAINS.get(event.symbol)
        try:
            rec = evaluate_earnings_setup(
                event,
                chain,
                normal_paper_risk_usd=normal_paper_risk_usd,
                micro_fraction=micro_fraction,
            )
            recommendations.append(rec)
        except Exception as exc:
            logger.warning("Earnings evaluate failed for %s: %s", event.symbol, exc)

    upcoming = [e.to_dict() for e in FIXTURE_EVENTS if e.phase != EarningsPhase.EXPIRED]
    pre = [
        r.to_dict()
        for r in recommendations
        if r.phase in (EarningsPhase.PRE_EARNINGS, EarningsPhase.WAITING_FOR_REPORT)
    ]
    post = [
        r.to_dict()
        for r in recommendations
        if r.phase
        in (EarningsPhase.POST_RELEASE_UNCONFIRMED, EarningsPhase.POST_EARNINGS_CONFIRMED)
    ]
    micros = [r.to_dict() for r in recommendations if r.recommendation == EarningsRecType.MICRO_COATTAIL]
    reviewed = [r.to_dict() for r in recommendations]

    return {
        "upcoming": upcoming,
        "watchlist": fixture_watchlist(),
        "pre_earnings": pre,
        "post_earnings": post,
        "micro_coattails": micros,
        "recently_reviewed": reviewed,
        "counts": {
            "upcoming": len(upcoming),
            "pre": len(pre),
            "post": len(post),
            "micro": len(micros),
            "reviewed": len(reviewed),
        },
        "paper_only": True,
        "live_trading_enabled": False,
        "config": {
            "normal_paper_risk_usd": normal_paper_risk_usd,
            "micro_coattail_fraction": micro_fraction,
            "micro_max_risk_usd": round(normal_paper_risk_usd * micro_fraction, 2),
        },
        "freshness": build_freshness(
            provider_name="Earnings Fixture Desk",
            data_timestamp=utcnow(),
            data_status=DataStatus.SIMULATED,
        ).to_dict(),
        "disclaimer": (
            "Earnings Intelligence is paper-only decision support. Fixtures are labelled simulated. "
            "OTM/Micro-Coattail requires positive expected value after costs — headline % return cannot "
            "override failed liquidity, breakeven, or risk checks. No live order routing."
        ),
        "audit": {
            "feature": "earnings_intelligence",
            "paper_only": True,
            "live_trading_enabled": False,
            "score_version": "earnings_setup_v1",
            "generated_at": utcnow().isoformat(),
        },
    }


def record_earnings_outcome_payload(
    *,
    recommendation: dict[str, Any],
    actual_direction: str | None,
    actual_move_pct: float | None,
    actual_iv_crush_pct: float | None,
    paper_entry: float | None,
    paper_exit: float | None,
    mfe_pct: float | None,
    mae_pct: float | None,
    net_result_after_costs: float | None,
) -> dict[str, Any]:
    """Learning-loop payload — does not auto-change production policies."""
    return {
        "symbol": recommendation.get("symbol"),
        "recommendation_type": recommendation.get("recommendation"),
        "strategy": recommendation.get("strategy"),
        "predicted_direction": recommendation.get("direction"),
        "predicted_move_pct": recommendation.get("expected_move_pct"),
        "predicted_iv_crush_pct": recommendation.get("estimated_iv_crush_pct"),
        "actual_direction": actual_direction,
        "actual_move_pct": actual_move_pct,
        "actual_iv_crush_pct": actual_iv_crush_pct,
        "paper_entry": paper_entry,
        "paper_exit": paper_exit,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "net_result_after_costs": net_result_after_costs,
        "confidence_at_signal": recommendation.get("confidence"),
        "micro_coattail": recommendation.get("recommendation") == "MICRO_COATTAIL",
        "paper_only": True,
        "policy_auto_update": False,
        "recorded_at": utcnow().isoformat(),
    }
