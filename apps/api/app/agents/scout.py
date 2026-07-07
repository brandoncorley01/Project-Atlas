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
        if candidate.open_interest < min_oi:
            continue
        if candidate.volume < min_vol:
            continue
        if candidate.bid_ask_spread_pct > max_spread:
            continue
        if candidate.days_to_expiration < 1:
            continue
        passed.append(candidate)

    return passed
