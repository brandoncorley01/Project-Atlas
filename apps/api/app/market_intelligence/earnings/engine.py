"""Earnings recommendation engine — paper-only, EV-disciplined."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.market_intelligence.earnings.ev import (
    breakeven_pct_for_call,
    breakeven_pct_for_put,
    estimate_trade_costs,
    expected_value,
    liquidity_ok,
    micro_coattail_size,
    otm_passes_gates,
    reachable_breakeven,
)
from app.market_intelligence.earnings.expected_move import (
    blend_expected_move,
    estimate_iv_crush_pct,
    expected_move_from_iv,
    expected_move_from_straddle,
    historical_avg_move,
)
from app.market_intelligence.earnings.types import (
    ContractCandidate,
    EarningsDirection,
    EarningsEvent,
    EarningsPhase,
    EarningsRecType,
    EarningsRecommendation,
    EarningsStrategy,
    StrategyComparison,
)
from app.market_intelligence.freshness import utcnow
from app.market_intelligence.scoring.versions import EARNINGS_SETUP_V1


def _pop_estimate(expected_move: float | None, breakeven: float | None, direction_edge: bool) -> float:
    """Heuristic PoP — never claim precision without distribution data."""
    if expected_move is None or expected_move <= 0:
        return 0.35
    if breakeven is None:
        return 0.40 if direction_edge else 0.35
    ratio = abs(breakeven) / expected_move
    if ratio <= 0.55:
        base = 0.58
    elif ratio <= 0.75:
        base = 0.50
    elif ratio <= 0.95:
        base = 0.44
    else:
        base = 0.32
    return base if direction_edge else max(0.28, base - 0.08)


def _direction_for(event: EarningsEvent) -> EarningsDirection:
    sent = (event.analyst_sentiment or "").lower()
    sector = (event.sector_direction or "").lower()
    if event.phase in (EarningsPhase.POST_RELEASE_UNCONFIRMED, EarningsPhase.POST_EARNINGS_CONFIRMED):
        if event.eps_actual is not None and event.eps_estimate is not None:
            if event.eps_actual > event.eps_estimate and sector in ("leading", "strengthening", "constructive"):
                return EarningsDirection.BULLISH
            if event.eps_actual < event.eps_estimate:
                return EarningsDirection.BEARISH
    if sent == "bullish" and sector in ("leading", "strengthening", "constructive"):
        return EarningsDirection.BULLISH
    if sent == "bearish" or sector in ("weakening", "lagging"):
        return EarningsDirection.BEARISH
    if sent == "mixed":
        return EarningsDirection.NEUTRAL
    return EarningsDirection.NO_EDGE


def evaluate_earnings_setup(
    event: EarningsEvent,
    chain: dict[str, Any] | None,
    *,
    normal_paper_risk_usd: float = 100.0,
    micro_fraction: float = 0.18,
    max_spread_pct: float = 12.0,
) -> EarningsRecommendation:
    """
    Produce an explainable recommendation.
    Missing/stale critical data → INSUFFICIENT_DATA (never invent a qualified trade).
    Paper-only — live_trading_enabled is always False.
    """
    now = utcnow()
    critical_missing = [
        f
        for f in (event.missing_fields or [])
        if f in ("eps_estimate", "options_chain", "iv", "historical_moves", "price")
    ]
    if event.stale or event.price is None or event.price <= 0:
        return _insufficient(event, now, "Price or core quote data missing/stale.")
    if event.stale or (not chain and "options_chain" in (event.missing_fields or [])):
        return _insufficient(event, now, "Options chain unavailable — cannot score EV.")
    if not chain:
        return _insufficient(event, now, "No options chain context for this symbol.")
    if critical_missing and not chain.get("contracts"):
        return _insufficient(event, now, f"Critical fields missing: {', '.join(critical_missing)}")

    hist = historical_avg_move(event.historical_moves_pct)
    straddle = expected_move_from_straddle(
        price=float(event.price),
        call_mid=chain.get("straddle_call_mid"),
        put_mid=chain.get("straddle_put_mid"),
    )
    iv_move = expected_move_from_iv(
        price=float(event.price),
        iv=chain.get("atm_iv"),
        days_to_event=1.0,
    )
    blended = blend_expected_move(straddle_pct=straddle, iv_pct=iv_move, historical_pct=hist)
    expected_move = blended["expected_move_pct"]
    iv_crush = estimate_iv_crush_pct(
        pre_iv=chain.get("atm_iv"),
        historical_crush=chain.get("historical_iv_crush"),
    )

    if expected_move is None:
        return _insufficient(event, now, "Could not form an expected-move estimate.")

    direction = _direction_for(event)
    contracts: list[ContractCandidate] = list(chain.get("contracts") or [])
    otm = next((c for c in contracts if c.moneyness == "otm"), None)
    atm = next((c for c in contracts if c.moneyness == "atm"), None)

    alternatives: list[StrategyComparison] = []
    # No trade baseline
    alternatives.append(
        StrategyComparison(
            strategy=EarningsStrategy.NO_TRADE,
            rank=99,
            expected_value=0.0,
            probability_of_profit=None,
            max_loss=0.0,
            breakeven_pct=0.0,
            note="Default when edge is not positive after costs.",
        )
    )
    alternatives.append(
        StrategyComparison(
            strategy=EarningsStrategy.WAIT_POST_CONFIRM,
            rank=50,
            expected_value=None,
            probability_of_profit=None,
            max_loss=0.0,
            breakeven_pct=None,
            note="Wait for opening-range / VWAP / relative-volume confirmation after the print.",
        )
    )

    # Evaluate OTM if present
    otm_eval = _evaluate_contract(
        event,
        otm,
        expected_move=expected_move,
        hist=hist,
        direction=direction,
        normal_paper_risk_usd=normal_paper_risk_usd,
        micro_fraction=micro_fraction,
        max_spread_pct=max_spread_pct,
        iv_crush=iv_crush,
    )
    atm_eval = _evaluate_contract(
        event,
        atm,
        expected_move=expected_move,
        hist=hist,
        direction=direction,
        normal_paper_risk_usd=normal_paper_risk_usd,
        micro_fraction=micro_fraction,
        max_spread_pct=max_spread_pct,
        iv_crush=iv_crush,
        prefer_atm=True,
    )

    if otm_eval["comparison"]:
        alternatives.append(otm_eval["comparison"])
    if atm_eval["comparison"]:
        alternatives.append(atm_eval["comparison"])

    # Debit spread conceptual comparison (defined risk)
    spread_ev = None
    if otm_eval.get("ev") is not None:
        spread_ev = round(float(otm_eval["ev"]) * 0.85 + 2.0, 2)  # slightly better risk profile heuristic
    alternatives.append(
        StrategyComparison(
            strategy=EarningsStrategy.DEBIT_SPREAD,
            rank=3 if spread_ev and spread_ev > 0 else 40,
            expected_value=spread_ev,
            probability_of_profit=otm_eval.get("pop"),
            max_loss=round(normal_paper_risk_usd * micro_fraction, 2),
            breakeven_pct=otm_eval.get("breakeven"),
            note="Defined-risk debit spread often ranks above naked OTM when IV crush is elevated.",
            rejected=spread_ev is None or spread_ev <= 0,
            reject_reason=None if spread_ev and spread_ev > 0 else "No clear positive EV vs no-trade",
        )
    )

    # Shares comparison
    alternatives.append(
        StrategyComparison(
            strategy=EarningsStrategy.SHARES,
            rank=20,
            expected_value=None,
            probability_of_profit=0.5,
            max_loss=round(float(event.price) * 0.08 * 10, 2),  # illustrative 10-share adverse
            breakeven_pct=0.0,
            note="Shares avoid IV crush but require larger capital and gap risk.",
            rejected=True,
            reject_reason="Capital and gap risk exceed paper Micro-Coattail mandate for this desk",
        )
    )

    # Phase-specific handling
    if event.phase == EarningsPhase.POST_RELEASE_UNCONFIRMED:
        return _watch(
            event,
            now,
            direction=direction,
            expected_move=expected_move,
            hist=hist,
            iv_crush=iv_crush,
            summary="Print is out but move is unconfirmed — waiting for opening range, VWAP, and relative volume.",
            watching=[
                "Opening range hold/fail",
                "VWAP reclaim or rejection",
                "Relative volume vs 20-day",
                "Guidance language vs sector confirmation",
            ],
            confirmation="Price holds opening range with RVOL > 1.5 and sector confirmation",
            expires_hours=6,
            alternatives=alternatives,
            paper_size=round(normal_paper_risk_usd * micro_fraction, 2),
        )

    if event.phase == EarningsPhase.WAITING_FOR_REPORT:
        return _watch(
            event,
            now,
            direction=direction,
            expected_move=expected_move,
            hist=hist,
            iv_crush=iv_crush,
            summary="Report window is open / imminent — no new risk until numbers and guidance print.",
            watching=["EPS vs estimate", "Revenue vs estimate", "Guidance tone", "Immediate AH reaction quality"],
            confirmation="Numbers + guidance released; AH move not treated as confirmed",
            expires_hours=12,
            alternatives=alternatives,
            paper_size=0.0,
        )

    # Choose best actionable
    otm_ok = bool(otm_eval.get("passes"))
    atm_ok = bool(atm_eval.get("passes"))
    spread_ok = spread_ev is not None and spread_ev > 0

    score = {
        "score_key": "earnings_setup",
        "score_version": EARNINGS_SETUP_V1,
        "expected_move_source": blended.get("source"),
        "expected_move_inputs": blended.get("inputs"),
        "otm_gates": otm_eval.get("gates"),
        "paper_only": True,
        "live_trading_enabled": False,
    }

    if not otm_ok and not atm_ok and not spread_ok:
        # Weak OTM rejected path
        if otm is not None and otm_eval.get("gates") and not otm_eval["gates"].get("liquidity_ok"):
            return _avoid(
                event,
                now,
                direction=direction,
                expected_move=expected_move,
                hist=hist,
                iv_crush=iv_crush,
                summary="OTM liquidity/spread fails — large theoretical % return does not qualify.",
                why="Weak volume/OI or wide bid-ask; EV after costs is not reliable.",
                alternatives=alternatives,
                score=score,
            )
        if direction == EarningsDirection.NO_EDGE:
            return _avoid(
                event,
                now,
                direction=direction,
                expected_move=expected_move,
                hist=hist,
                iv_crush=iv_crush,
                summary="No directional edge after sector/sentiment checks.",
                why="Without edge, no-trade ranks first.",
                alternatives=alternatives,
                score=score,
            )
        return _watch(
            event,
            now,
            direction=direction,
            expected_move=expected_move,
            hist=hist,
            iv_crush=iv_crush,
            summary="Setup is interesting but confirmation or cleaner structure is required.",
            watching=["IV term structure", "Sector confirmation", "Liquidity improvement", "Guidance preview"],
            confirmation="Positive EV structure with acceptable spread and reachable breakeven",
            expires_hours=48,
            alternatives=alternatives,
            paper_size=0.0,
            score=score,
        )

    # Prefer debit spread narrative when crush elevated and OTM borderline
    prefer_spread = bool(iv_crush and iv_crush >= 30 and spread_ok)
    if prefer_spread or (spread_ok and not otm_ok):
        size = micro_coattail_size(
            normal_paper_risk_usd=normal_paper_risk_usd,
            fraction=micro_fraction,
            max_loss_per_contract=normal_paper_risk_usd * micro_fraction,
        )
        return EarningsRecommendation(
            symbol=event.symbol,
            recommendation=EarningsRecType.MICRO_COATTAIL
            if direction != EarningsDirection.BULLISH or (otm_eval.get("confidence", 0) < 70)
            else EarningsRecType.QUALIFIED_TRADE,
            direction=direction if direction != EarningsDirection.NO_EDGE else EarningsDirection.NEUTRAL,
            phase=event.phase,
            strategy=EarningsStrategy.DEBIT_SPREAD,
            confidence=float(otm_eval.get("confidence") or 60),
            expected_move_pct=expected_move,
            historical_avg_move_pct=hist,
            estimated_iv_crush_pct=iv_crush,
            breakeven_pct=otm_eval.get("breakeven"),
            probability_of_profit=otm_eval.get("pop"),
            expected_value=spread_ev,
            max_loss=size["paper_position_size_usd"],
            paper_position_size_usd=size["paper_position_size_usd"],
            entry_condition="Enter only if spread mid is within 5% of evaluated mark and sector confirms.",
            invalidation_condition="Break of pre-earnings support or guidance cut after print.",
            profit_targets=["1× credit width", "Close 50% at +40% of debit"],
            expected_holding_period="Through print + 1 session, or until IV crush realizes",
            watching=["IV crush realization", "Sector confirmation", "Guidance vs estimate"],
            why_strategy="Debit spread caps max loss and ranks above naked OTM when IV crush is elevated.",
            why_not_full_size="Earnings uncertainty and IV crush keep size at Micro-Coattail.",
            upgrade_condition="Post-print confirmation with RVOL and sector alignment → QUALIFIED_TRADE.",
            downgrade_condition="Spread widens >12% or EV turns negative after costs.",
            cancel_condition="Thesis invalidated by guidance miss or sector breakdown.",
            summary="Atlas found a small positive edge, but earnings uncertainty remains elevated.",
            alternatives=_rank_alts(alternatives),
            contract=otm,
            score=score,
            data_status=event.data_status,
            paper_only=True,
            evaluated_at=now,
        )

    # Naked OTM that passed all gates
    chosen = otm_eval if otm_ok else atm_eval
    conf = float(chosen.get("confidence") or 55)
    rec_type = (
        EarningsRecType.QUALIFIED_TRADE
        if conf >= 70 and chosen.get("ev", 0) > 5 and direction in (EarningsDirection.BULLISH, EarningsDirection.BEARISH)
        else EarningsRecType.MICRO_COATTAIL
    )
    size = micro_coattail_size(
        normal_paper_risk_usd=normal_paper_risk_usd,
        fraction=micro_fraction if rec_type == EarningsRecType.MICRO_COATTAIL else min(0.35, micro_fraction * 2),
        max_loss_per_contract=chosen.get("max_loss"),
    )
    return EarningsRecommendation(
        symbol=event.symbol,
        recommendation=rec_type,
        direction=direction if direction != EarningsDirection.NO_EDGE else EarningsDirection.NEUTRAL,
        phase=event.phase,
        strategy=EarningsStrategy.OTM_OPTION if otm_ok else EarningsStrategy.ATM_OPTION,
        confidence=conf,
        expected_move_pct=expected_move,
        historical_avg_move_pct=hist,
        estimated_iv_crush_pct=iv_crush,
        breakeven_pct=chosen.get("breakeven"),
        probability_of_profit=chosen.get("pop"),
        expected_value=chosen.get("ev"),
        max_loss=chosen.get("max_loss"),
        paper_position_size_usd=size["paper_position_size_usd"],
        entry_condition="Fill near evaluated mid; abort if spread widens beyond limit.",
        invalidation_condition="Move envelope fails (price stalls inside breakeven) or guidance shock opposite thesis.",
        profit_targets=["+40% of debit", "+80% of debit or expected-move touch"],
        expected_holding_period="Pre-print through 1 session post-print",
        watching=["Implied move vs realized", "IV crush", "Sector confirmation"],
        why_strategy=chosen.get("why") or "Selected for reachable breakeven and positive EV after costs.",
        why_not_full_size="Micro size until learning loop proves Micro-Coattail edge.",
        upgrade_condition="Higher confidence with cleaner liquidity and sector confirmation.",
        downgrade_condition="EV ≤ 0 after updated IV/spread or thesis softens.",
        cancel_condition="Liquidity fails or expected move collapses below breakeven.",
        summary=(
            "Atlas found a small positive edge, but earnings uncertainty remains elevated."
            if rec_type == EarningsRecType.MICRO_COATTAIL
            else "Setup clears EV, liquidity, and breakeven checks for a qualified paper trade."
        ),
        alternatives=_rank_alts(alternatives),
        contract=chosen.get("contract"),
        score=score,
        data_status=event.data_status,
        paper_only=True,
        evaluated_at=now,
    )


def _evaluate_contract(
    event: EarningsEvent,
    contract: ContractCandidate | None,
    *,
    expected_move: float,
    hist: float | None,
    direction: EarningsDirection,
    normal_paper_risk_usd: float,
    micro_fraction: float,
    max_spread_pct: float,
    iv_crush: float | None,
    prefer_atm: bool = False,
) -> dict[str, Any]:
    empty = {
        "passes": False,
        "comparison": None,
        "ev": None,
        "pop": None,
        "breakeven": None,
        "max_loss": None,
        "confidence": 0,
        "gates": {},
        "contract": None,
        "why": None,
    }
    if contract is None or event.price is None:
        return empty

    liq_ok, liq_reasons = liquidity_ok(
        volume=contract.volume,
        open_interest=contract.open_interest,
        spread=contract.spread_pct,
        max_spread_pct=max_spread_pct,
    )
    if contract.option_type == "put":
        be = breakeven_pct_for_put(premium=contract.premium, strike=contract.strike, spot=float(event.price))
    else:
        be = breakeven_pct_for_call(premium=contract.premium, strike=contract.strike, spot=float(event.price))

    reach_ok, reach_note = reachable_breakeven(
        breakeven_pct=be,
        expected_move_pct=expected_move,
        historical_avg_pct=hist,
        modeled_range_pct=expected_move,
    )
    direction_edge = direction in (EarningsDirection.BULLISH, EarningsDirection.BEARISH)
    pop = _pop_estimate(expected_move, be, direction_edge)
    max_loss = round(contract.premium * 100.0, 2)  # 1 contract
    costs = estimate_trade_costs(premium=contract.premium, spread_pct_val=contract.spread_pct, contracts=1)
    # Crush haircut on expected gain
    crush_haircut = 1.0 - ((iv_crush or 25.0) / 100.0) * 0.35
    avg_gain = round(max_loss * 1.6 * crush_haircut, 2)
    avg_loss = max_loss
    ev = expected_value(
        probability_of_profit=pop,
        avg_gain=avg_gain,
        avg_loss=avg_loss,
        estimated_costs=costs,
    )
    within_risk = max_loss <= normal_paper_risk_usd
    gates = {
        "liquidity_ok": liq_ok,
        "breakeven_reachable": reach_ok,
        "positive_ev": ev > 0,
        "max_loss_defined": max_loss > 0,
        "within_risk_limit": within_risk,
        "liquidity_reasons": liq_reasons,
        "breakeven_note": reach_note,
        "ev": ev,
        "costs": costs,
    }
    passes, fail_keys = otm_passes_gates(gates)
    # ATM can pass with slightly looser narrative but same gates
    if prefer_atm and passes:
        pass

    conf = 50.0
    if passes:
        conf = 62.0 + (8.0 if direction_edge else 0) + (5.0 if liq_ok and reach_ok else 0)
        conf = min(78.0, conf)
    comparison = StrategyComparison(
        strategy=EarningsStrategy.ATM_OPTION if prefer_atm else EarningsStrategy.OTM_OPTION,
        rank=2 if passes else 60,
        expected_value=ev,
        probability_of_profit=round(pop * 100.0, 1),
        max_loss=max_loss,
        breakeven_pct=be,
        note=reach_note if passes else f"Rejected: {', '.join(fail_keys) or 'gates'}",
        rejected=not passes,
        reject_reason=None if passes else ", ".join(fail_keys + liq_reasons)[:180],
    )
    return {
        "passes": passes,
        "comparison": comparison,
        "ev": ev,
        "pop": round(pop * 100.0, 1),
        "breakeven": be,
        "max_loss": max_loss,
        "confidence": conf,
        "gates": gates,
        "contract": contract,
        "why": (
            "OTM clears liquidity, reachable breakeven, and positive EV after spread/slippage/IV-crush costs."
            if passes and not prefer_atm
            else "ATM structure preferred when OTM fails reachability or liquidity."
            if passes
            else None
        ),
    }


def _rank_alts(alts: list[StrategyComparison]) -> list[StrategyComparison]:
    return sorted(alts, key=lambda a: (a.rejected, a.rank, -(a.expected_value or -999)))


def _insufficient(event: EarningsEvent, now: datetime, reason: str) -> EarningsRecommendation:
    return EarningsRecommendation(
        symbol=event.symbol,
        recommendation=EarningsRecType.INSUFFICIENT_DATA,
        direction=EarningsDirection.NO_EDGE,
        phase=event.phase,
        strategy=EarningsStrategy.NO_TRADE,
        confidence=0.0,
        expected_move_pct=None,
        historical_avg_move_pct=historical_avg_move(event.historical_moves_pct),
        estimated_iv_crush_pct=None,
        breakeven_pct=None,
        probability_of_profit=None,
        expected_value=None,
        max_loss=0.0,
        paper_position_size_usd=0.0,
        entry_condition="n/a",
        invalidation_condition="n/a",
        profit_targets=[],
        expected_holding_period="n/a",
        watching=["Restore missing/stale inputs before scoring"],
        why_strategy="Reliable analysis cannot be completed.",
        why_not_full_size=reason,
        upgrade_condition="Provide expected move, IV, and liquid chain data.",
        downgrade_condition="n/a",
        cancel_condition="n/a",
        summary=reason,
        alternatives=[],
        data_status=event.data_status,
        paper_only=True,
        evaluated_at=now,
    )


def _avoid(
    event: EarningsEvent,
    now: datetime,
    *,
    direction: EarningsDirection,
    expected_move: float | None,
    hist: float | None,
    iv_crush: float | None,
    summary: str,
    why: str,
    alternatives: list[StrategyComparison],
    score: dict[str, Any] | None = None,
) -> EarningsRecommendation:
    return EarningsRecommendation(
        symbol=event.symbol,
        recommendation=EarningsRecType.AVOID,
        direction=direction,
        phase=event.phase,
        strategy=EarningsStrategy.NO_TRADE,
        confidence=55.0,
        expected_move_pct=expected_move,
        historical_avg_move_pct=hist,
        estimated_iv_crush_pct=iv_crush,
        breakeven_pct=None,
        probability_of_profit=None,
        expected_value=0.0,
        max_loss=0.0,
        paper_position_size_usd=0.0,
        entry_condition="Do not enter.",
        invalidation_condition="n/a",
        profit_targets=[],
        expected_holding_period="n/a",
        watching=["Re-score if liquidity or edge improves"],
        why_strategy=why,
        why_not_full_size=summary,
        upgrade_condition="Positive EV structure with confirmation.",
        downgrade_condition="n/a",
        cancel_condition="n/a",
        summary=summary,
        alternatives=_rank_alts(alternatives),
        score=score,
        data_status=event.data_status,
        paper_only=True,
        evaluated_at=now,
    )


def _watch(
    event: EarningsEvent,
    now: datetime,
    *,
    direction: EarningsDirection,
    expected_move: float | None,
    hist: float | None,
    iv_crush: float | None,
    summary: str,
    watching: list[str],
    confirmation: str,
    expires_hours: int,
    alternatives: list[StrategyComparison],
    paper_size: float,
    score: dict[str, Any] | None = None,
) -> EarningsRecommendation:
    expires = (now + timedelta(hours=expires_hours)).isoformat()
    return EarningsRecommendation(
        symbol=event.symbol,
        recommendation=EarningsRecType.WATCH,
        direction=direction,
        phase=event.phase,
        strategy=EarningsStrategy.WAIT_POST_CONFIRM
        if event.phase
        in (EarningsPhase.POST_RELEASE_UNCONFIRMED, EarningsPhase.WAITING_FOR_REPORT)
        else EarningsStrategy.NO_TRADE,
        confidence=58.0,
        expected_move_pct=expected_move,
        historical_avg_move_pct=hist,
        estimated_iv_crush_pct=iv_crush,
        breakeven_pct=None,
        probability_of_profit=None,
        expected_value=None,
        max_loss=0.0,
        paper_position_size_usd=paper_size,
        entry_condition="No entry until confirmation condition hits.",
        invalidation_condition="Opposite guidance shock or sector breakdown.",
        profit_targets=[],
        expected_holding_period=f"Watch window {expires_hours}h",
        watching=watching,
        why_strategy="Promising but waiting for confirmation — first AH/open move is not treated as confirmed.",
        why_not_full_size=summary,
        upgrade_condition=confirmation,
        downgrade_condition="Confirmation fails or EV turns negative.",
        cancel_condition=f"Watch expires at {expires}",
        summary=summary,
        alternatives=_rank_alts(alternatives),
        score=score,
        data_status=event.data_status,
        paper_only=True,
        evaluated_at=now,
        watch_expires_at=expires,
        confirmation_condition=confirmation,
    )
