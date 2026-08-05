"""Assemble Earnings Intelligence desk payloads from live Yahoo market data."""

from __future__ import annotations

import logging
from typing import Any

from app.market_intelligence.earnings.engine import evaluate_earnings_setup
from app.market_intelligence.earnings.fixture_data import FIXTURE_CHAINS, FIXTURE_EVENTS
from app.market_intelligence.earnings.types import EarningsPhase, EarningsRecType
from app.market_intelligence.earnings.yahoo_provider import fetch_live_earnings_desk
from app.market_intelligence.freshness import build_freshness, utcnow
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)


def _pack_desk(
    events: list[Any],
    chains: dict[str, dict[str, Any]],
    *,
    normal_risk_usd: float,
    micro_fraction: float,
    meta: dict[str, Any],
) -> dict[str, Any]:
    recommendations = []
    for event in events:
        chain = chains.get(event.symbol)
        try:
            rec = evaluate_earnings_setup(
                event,
                chain,
                normal_risk_usd=normal_risk_usd,
                micro_fraction=micro_fraction,
            )
            recommendations.append(rec)
        except Exception as exc:
            logger.warning("Earnings evaluate failed for %s: %s", event.symbol, exc)

    upcoming = [e.to_dict() for e in events if e.phase != EarningsPhase.EXPIRED]
    watchlist = [
        {
            "symbol": e.symbol,
            "report_date": e.report_date.isoformat(),
            "phase": e.phase.value,
            "note": "Active earnings watch",
        }
        for e in events
        if e.phase != EarningsPhase.EXPIRED
    ]
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

    status = meta.get("data_status") or DataStatus.DELAYED.value
    try:
        data_status = DataStatus(status)
    except Exception:
        data_status = DataStatus.DELAYED

    return {
        "upcoming": upcoming,
        "watchlist": watchlist,
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
        "config": {
            "normal_risk_usd": normal_risk_usd,
            "micro_coattail_fraction": micro_fraction,
            "micro_max_risk_usd": round(normal_risk_usd * micro_fraction, 2),
        },
        "freshness": build_freshness(
            provider_name=str(meta.get("provider") or "yahoo_earnings"),
            data_timestamp=utcnow(),
            data_status=data_status,
        ).to_dict(),
        "disclaimer": (
            "Earnings Intelligence uses real Yahoo calendar, quotes, and options chains (delayed). "
            "OTM/Micro-Coattail requires positive expected value after costs — headline % return "
            "cannot override failed liquidity, breakeven, or risk checks."
        ),
        "audit": {
            "feature": "earnings_intelligence",
            "data_source": meta.get("provider") or "yahoo_earnings",
            "symbol_count": meta.get("symbol_count"),
            "with_chains": meta.get("with_chains"),
            "score_version": "earnings_setup_v1",
            "generated_at": utcnow().isoformat(),
        },
        "source": meta.get("provider") or "yahoo_earnings",
    }


async def build_earnings_desk(
    *,
    normal_risk_usd: float = 100.0,
    micro_fraction: float = 0.18,
    allow_fixture_fallback: bool = False,
) -> dict[str, Any]:
    """
    Full desk from live Yahoo data. Fixture fallback only if the live scan returns nothing
    and fallback is allowed (labelled simulated).
    """
    try:
        events, chains, meta = await fetch_live_earnings_desk()
        if events:
            return _pack_desk(
                events,
                chains,
                normal_risk_usd=normal_risk_usd,
                micro_fraction=micro_fraction,
                meta=meta,
            )
        logger.warning("Live earnings desk empty: %s", meta.get("note"))
    except Exception as exc:
        logger.warning("Live earnings desk failed: %s", exc)
        meta = {"provider": "yahoo_earnings", "data_status": DataStatus.PARTIAL.value, "note": str(exc)}

    if not allow_fixture_fallback:
        return {
            "upcoming": [],
            "watchlist": [],
            "pre_earnings": [],
            "post_earnings": [],
            "micro_coattails": [],
            "recently_reviewed": [],
            "config": {
                "normal_risk_usd": normal_risk_usd,
                "micro_coattail_fraction": micro_fraction,
                "micro_max_risk_usd": round(normal_risk_usd * micro_fraction, 2),
            },
            "freshness": build_freshness(
                provider_name="yahoo_earnings",
                data_timestamp=None,
                data_status=DataStatus.PARTIAL,
                missing_fields=["earnings_calendar"],
            ).to_dict(),
            "disclaimer": "Live earnings data unavailable.",
            "audit": {"feature": "earnings_intelligence", "generated_at": utcnow().isoformat()},
            "source": "yahoo_earnings",
        }

    # Deterministic fallback for offline / cold start — never preferred
    return _pack_desk(
        FIXTURE_EVENTS,
        FIXTURE_CHAINS,
        normal_risk_usd=normal_risk_usd,
        micro_fraction=micro_fraction,
        meta={
            "provider": "earnings_fixture_fallback",
            "data_status": DataStatus.SIMULATED.value,
            "symbol_count": len(FIXTURE_EVENTS),
            "with_chains": len(FIXTURE_CHAINS),
            "note": "Fallback fixtures — live Yahoo scan returned no rows",
        },
    )


def record_earnings_outcome_payload(
    *,
    recommendation: dict[str, Any],
    actual_direction: str | None,
    actual_move_pct: float | None,
    actual_iv_crush_pct: float | None,
    entry: float | None,
    exit: float | None,
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
        "entry": entry,
        "exit": exit,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "net_result_after_costs": net_result_after_costs,
        "confidence_at_signal": recommendation.get("confidence"),
        "micro_coattail": recommendation.get("recommendation") == "MICRO_COATTAIL",
        "policy_auto_update": False,
        "recorded_at": utcnow().isoformat(),
    }
