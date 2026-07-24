"""Signal outcome tracking without hindsight leakage into original scores."""

from __future__ import annotations

from typing import Any


def compute_outcome_metrics(
    *,
    entry_underlying: float,
    entry_contract: float | None,
    underlying_path: list[float],
    contract_path: list[float] | None = None,
    stop_pct: float = -50.0,
) -> dict[str, Any]:
    """
    Paths are subsequent observations AFTER signal time only.
    Do not include pre-signal data.
    """
    if not underlying_path or entry_underlying <= 0:
        return {
            "evaluation_status": "insufficient_data",
            "data_completeness": "incomplete",
        }

    u_high = max(underlying_path)
    u_low = min(underlying_path)
    # Direction-agnostic excursion vs underlying entry
    mfe = (u_high - entry_underlying) / entry_underlying * 100
    mae = (u_low - entry_underlying) / entry_underlying * 100

    contract_high = contract_low = None
    hit_25 = hit_50 = hit_100 = hit_200 = hit_stop = False
    if contract_path and entry_contract and entry_contract > 0:
        contract_high = max(contract_path)
        contract_low = min(contract_path)
        rets = [(p - entry_contract) / entry_contract * 100 for p in contract_path]
        peak = max(rets)
        trough = min(rets)
        hit_25 = peak >= 25
        hit_50 = peak >= 50
        hit_100 = peak >= 100
        hit_200 = peak >= 200
        hit_stop = trough <= stop_pct
        mfe = peak
        mae = trough

    time_to_mfe = None
    if contract_path and entry_contract and entry_contract > 0:
        rets = [(p - entry_contract) / entry_contract * 100 for p in contract_path]
        peak = max(rets)
        time_to_mfe = rets.index(peak)  # bars since detection; caller maps to hours
    else:
        rel = [(p - entry_underlying) / entry_underlying * 100 for p in underlying_path]
        peak = max(rel)
        time_to_mfe = rel.index(peak)

    return {
        "underlying_high": u_high,
        "underlying_low": u_low,
        "contract_high": contract_high,
        "contract_low": contract_low,
        "mfe_pct": round(mfe, 4),
        "mae_pct": round(mae, 4),
        "time_to_mfe_bars": time_to_mfe,
        "hit_25": hit_25,
        "hit_50": hit_50,
        "hit_100": hit_100,
        "hit_200": hit_200,
        "hit_stop": hit_stop,
        "evaluation_status": "evaluated",
        "data_completeness": "complete" if contract_path else "partial",
    }
