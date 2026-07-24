"""Sector rotation + Market Weather classifiers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.market_intelligence.scoring.versions import WEATHER_V1, WEATHER_WEIGHTS
from app.market_intelligence.types import SectorClass, ScoreBreakdown


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def classify_sector(metrics: dict[str, Any]) -> tuple[SectorClass, list[str]]:
    """
    metrics: relative_return, breadth_above_ma, volume_rank, options_bias (-1..1),
             acceleration, data_points
    """
    evidence: list[str] = []
    points = int(metrics.get("data_points") or 0)
    if points < 3:
        return SectorClass.INSUFFICIENT_DATA, ["Fewer than 3 constituent observations"]

    rel = float(metrics.get("relative_return") or 0)
    breadth = float(metrics.get("breadth_above_ma") or 0.5)
    accel = float(metrics.get("acceleration") or 0)
    bias = float(metrics.get("options_bias") or 0)

    evidence.append(f"Relative return {rel:+.2f}%")
    evidence.append(f"Breadth above MA {breadth * 100:.0f}%")
    if bias:
        evidence.append(f"Options bias {bias:+.2f}")

    if rel > 1.5 and breadth >= 0.6 and accel >= 0:
        return SectorClass.LEADING, evidence
    if rel > 0.5 and accel > 0:
        return SectorClass.STRENGTHENING, evidence
    if rel < -1.5 and breadth <= 0.4 and accel <= 0:
        return SectorClass.LAGGING, evidence
    if rel < -0.5 and accel < 0:
        return SectorClass.WEAKENING, evidence
    return SectorClass.MIXED, evidence


def classify_market_weather(inputs: dict[str, Any], *, now: datetime | None = None) -> tuple[str, ScoreBreakdown, dict[str, Any]]:
    """
    Deterministic Market Weather — not a forecast guarantee.
    inputs: index_momentum, breadth, sector_leadership, options_bias, volatility_regime, news_sentiment
      each roughly -1..1 except volatility_regime (0 calm .. 1 stressed)
    """
    now = now or datetime.now(UTC)
    components: dict[str, float] = {}
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    def take(key: str, alias: str) -> float:
        val = inputs.get(key)
        if val is None:
            missing.append(key)
            components[alias] = 50.0
            return 0.0
        # Map -1..1 into bullishness score 0..100
        score = _clamp(50 + float(val) * 40)
        components[alias] = score
        return float(val)

    idx = take("index_momentum", "index")
    breadth = take("breadth", "breadth")
    sectors = take("sector_leadership", "sectors")
    options = take("options_bias", "options")
    news = take("news_sentiment", "news")

    vol = inputs.get("volatility_regime")
    if vol is None:
        missing.append("volatility_regime")
        components["volatility"] = 50.0
        vol_v = 0.5
    else:
        vol_v = float(vol)
        components["volatility"] = _clamp(100 - vol_v * 80)
        if vol_v > 0.7:
            negatives.append("Elevated volatility regime")
        else:
            positives.append("Volatility not stressed")

    # Composite bullishness (higher = more bullish weather)
    bull = 0.0
    for key, weight in WEATHER_WEIGHTS.items():
        if key == "volatility":
            bull += components[key] * weight
        else:
            bull += components[key] * weight

    if idx > 0.2:
        positives.append("Index momentum constructive")
    if idx < -0.2:
        negatives.append("Index momentum weak")
    if options > 0.2:
        positives.append("Options bias leans bullish")
    if options < -0.2:
        negatives.append("Options bias leans bearish")

    if bull >= 75:
        label = "Strongly bullish"
    elif bull >= 62:
        label = "Bullish"
    elif bull >= 54:
        label = "Cautiously bullish"
    elif bull >= 46:
        label = "Neutral"
    elif bull >= 38:
        label = "Cautiously bearish"
    elif bull >= 25:
        label = "Bearish"
    else:
        label = "High uncertainty"

    if len(missing) >= 3 or vol_v > 0.85:
        label = "High uncertainty"

    confidence = _clamp(85 - len(missing) * 10)
    risk = "elevated" if vol_v > 0.65 or bull < 40 else ("moderate" if bull < 55 else "contained")

    breakdown = ScoreBreakdown(
        score_key="market_weather",
        score_version=WEATHER_V1,
        final_score=bull,
        confidence=confidence,
        data_quality="high" if len(missing) <= 1 else ("medium" if len(missing) <= 3 else "low"),
        component_values=components,
        weights=dict(WEATHER_WEIGHTS),
        positive_contributors=positives,
        negative_contributors=negatives,
        missing_inputs=missing,
        penalties=[],
        evaluation_timestamp=now,
        data_timestamp=now,
        data_freshness="evaluated",
    )

    payload = {
        "label": label,
        "risk_level": risk,
        "strongest_sectors": inputs.get("strongest_sectors") or [],
        "weakest_sectors": inputs.get("weakest_sectors") or [],
        "favorable_environments": inputs.get("favorable_environments") or [],
        "areas_to_avoid": inputs.get("areas_to_avoid") or [],
        "supporting_evidence": positives,
        "main_risks": negatives,
        "disclaimer": (
            "Market Weather describes recent conditions and regime context. "
            "It is not a literal forecast and does not guarantee future movement."
        ),
    }
    return label, breakdown, payload
