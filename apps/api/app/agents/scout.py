from app.engine.models import CandidateOpportunity

MIN_OPEN_INTEREST = 200
MIN_VOLUME = 20
MAX_SPREAD_PCT = 10.0
MAX_PREMIUM = 10.0
MAX_CONTRACT_COST = 100.0  # Total cost per contract (premium × 100 shares)


def contract_cost(candidate: CandidateOpportunity) -> float:
    return round((candidate.premium or 0) * 100, 2)


def is_budget_contract(candidate: CandidateOpportunity) -> bool:
    return contract_cost(candidate) <= MAX_CONTRACT_COST


def open_interest_ok(
    open_interest: int | None,
    volume: int | None,
    *,
    min_oi: int = MIN_OPEN_INTEREST,
    min_volume: int = MIN_VOLUME,
    strict: bool = False,
) -> bool:
    """
    Liquidity gate for open interest.

    Yahoo Finance frequently returns openInterest=0 even on liquid names.
    Treat OI=0/None as unknown and accept a volume proxy instead of hard-failing
    the entire options deep scan.
    """
    oi = 0 if open_interest is None else int(open_interest)
    vol = 0 if volume is None else int(volume)
    if oi >= min_oi:
        return True
    if oi == 0:
        # Stronger volume required when OI is missing from the feed
        floor = max(min_volume, 200 if strict else 50)
        return vol >= floor
    return False


def filter_candidates(
    candidates: list[CandidateOpportunity],
    *,
    strict: bool = False,
) -> list[CandidateOpportunity]:
    """Scout AI — hard liquidity and quality gates."""
    min_oi = 500 if strict else MIN_OPEN_INTEREST
    min_vol = 50 if strict else MIN_VOLUME
    max_spread = 8.0 if strict else MAX_SPREAD_PCT
    max_premium = MAX_PREMIUM

    passed: list[CandidateOpportunity] = []

    for candidate in candidates:
        if candidate.premium is not None and candidate.premium > max_premium:
            continue
        if not open_interest_ok(
            candidate.open_interest,
            candidate.volume,
            min_oi=min_oi,
            min_volume=min_vol,
            strict=strict,
        ):
            continue
        if candidate.volume < min_vol:
            continue
        if candidate.bid_ask_spread_pct > max_spread:
            continue
        if candidate.days_to_expiration < 1:
            continue
        passed.append(candidate)

    return passed
