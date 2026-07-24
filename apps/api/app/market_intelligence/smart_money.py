"""Smart-money / concentrated-activity watchlist (language-safe)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.market_intelligence.scoring.options_activity import score_options_activity
from app.market_intelligence.types import DirectionLabel, NormalizedOptionsActivity


def build_smart_money_watchlist(
    events: list[NormalizedOptionsActivity],
    *,
    min_events: int = 2,
    min_premium: float = 50_000,
) -> list[dict[str, Any]]:
    by_ticker: dict[str, list[NormalizedOptionsActivity]] = defaultdict(list)
    for e in events:
        by_ticker[e.underlying].append(e)

    rows: list[dict[str, Any]] = []
    for ticker, group in by_ticker.items():
        if len(group) < min_events:
            # Still allow single institutional-sized prints with careful language
            total_prem = sum(float(e.estimated_premium or 0) for e in group)
            if total_prem < min_premium:
                continue

        directions: list[DirectionLabel] = []
        total_prem = 0.0
        strikes = set()
        expirations = set()
        evidence: list[str] = []
        best_score = 0.0
        best_conf = 0.0

        for e in group:
            breakdown, direction = score_options_activity(e, repeat_count=len(group))
            directions.append(direction)
            total_prem += float(e.estimated_premium or 0)
            strikes.add(str(e.strike))
            expirations.add(e.expiration.isoformat())
            best_score = max(best_score, breakdown.final_score)
            best_conf = max(best_conf, breakdown.confidence)

        dir_values = {d.value for d in directions}
        if DirectionLabel.UNCERTAIN in directions and len(dir_values) == 1:
            label = "Intent uncertain"
        elif DirectionLabel.POSSIBLE_HEDGE in directions:
            label = "Possible hedge"
        elif dir_values <= {"bullish"}:
            label = "Concentrated bullish activity" if len(group) >= 2 else "Institutional-sized activity"
        elif dir_values <= {"bearish"}:
            label = "Concentrated bearish activity" if len(group) >= 2 else "Institutional-sized activity"
        elif "bullish" in dir_values and "bearish" in dir_values:
            label = "Mixed directional activity"
        else:
            label = "Repeated directional activity"

        if len(strikes) >= 2:
            evidence.append(f"Activity across {len(strikes)} strikes")
        if len(expirations) >= 2:
            evidence.append(f"Activity across {len(expirations)} expirations")
        if len(group) >= 2:
            evidence.append(f"{len(group)} related prints")
        evidence.append(f"Combined premium ≈ ${total_prem:,.0f}")
        evidence.append("Large size does not prove smart money or institutional identity")

        rows.append(
            {
                "underlying": ticker,
                "label": label,
                "event_count": len(group),
                "total_premium": round(total_prem, 2),
                "unusual_score": round(best_score, 2),
                "confidence": round(best_conf, 2),
                "directions": sorted(dir_values),
                "evidence": evidence,
                "sector": group[0].sector,
                "data_status": group[0].data_status.value,
                "disclaimer": (
                    "Atlas does not identify institutions. Concentrated activity may be hedges or spreads."
                ),
            }
        )

    rows.sort(key=lambda r: (r["unusual_score"], r["total_premium"]), reverse=True)
    return rows
