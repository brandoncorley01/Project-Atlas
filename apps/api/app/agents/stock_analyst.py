"""Stock swing setup scoring — deterministic V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.providers.technicals import (
    compute_macd,
    compute_rsi,
    compute_sma,
    recent_range_pct,
    relative_volume,
)


@dataclass
class StockSwingSetup:
    symbol: str
    direction: str
    price: float
    entry_low: float
    entry_high: float
    stop_loss: float
    profit_targets: list[float]
    expected_hold_time: str
    timeframe: str
    technicals: dict[str, Any]
    confidence_score: float
    risk_score: float
    opportunity_score: float
    recommendation: str
    explanation: str
    bull_case: str
    bear_case: str
    invalidation: str
    suggested_action: str
    scoring_snapshot: dict[str, Any]


def _pct_diff(a: float, b: float) -> float:
    if b <= 0:
        return 0.0
    return abs(a - b) / b * 100


def _build_levels(
    *,
    direction: str,
    price: float,
    sma20: float | None,
    sma50: float | None,
    recent_high: float,
    recent_low: float,
    volatility_pct: float,
) -> tuple[float, float, float, list[float], str]:
    buffer = max(0.8, min(3.5, volatility_pct * 0.6))

    if direction == "bullish":
        anchor = sma20 if sma20 and price >= sma20 * 0.97 else price
        entry_low = round(anchor * (1 - buffer / 200), 2)
        entry_high = round(price * (1 + buffer / 300), 2)
        stop = round(min(recent_low, (sma20 or price) * (1 - buffer / 100)), 2)
        t1 = round(price * (1 + buffer / 100), 2)
        t2 = round(max(recent_high, price * (1 + buffer * 1.8 / 100)), 2)
        hold = "3-7 days" if volatility_pct >= 2.5 else "5-10 days"
        timeframe = "swing_short" if volatility_pct >= 2.5 else "swing_medium"
    else:
        anchor = sma20 if sma20 and price <= sma20 * 1.03 else price
        entry_low = round(price * (1 - buffer / 300), 2)
        entry_high = round(anchor * (1 + buffer / 200), 2)
        stop = round(max(recent_high, (sma20 or price) * (1 + buffer / 100)), 2)
        t1 = round(price * (1 - buffer / 100), 2)
        t2 = round(min(recent_low, price * (1 - buffer * 1.8 / 100)), 2)
        hold = "3-7 days" if volatility_pct >= 2.5 else "5-10 days"
        timeframe = "swing_short" if volatility_pct >= 2.5 else "swing_medium"

    return entry_low, entry_high, stop, [t1, t2], hold, timeframe


def analyze_swing(
    *,
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    catalyst: dict[str, Any] | None = None,
    chart_bars: list[dict[str, Any]] | None = None,
    min_setup_strength: float = 42.0,
) -> StockSwingSetup | None:
    if len(closes) < 30:
        return None

    price = closes[-1]
    rsi = compute_rsi(closes)
    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)
    macd = compute_macd(closes)
    rvol = relative_volume(volumes)
    vol_pct = recent_range_pct(closes)
    hist = macd.get("histogram") or 0.0
    prev_hist = 0.0
    if len(closes) >= 35:
        prev_macd = compute_macd(closes[:-1])
        prev_hist = prev_macd.get("histogram") or 0.0

    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    catalyst = catalyst or {}

    bullish = 0.0
    bearish = 0.0

    if sma20 and price > sma20:
        bullish += 18
    elif sma20 and price < sma20:
        bearish += 18

    if sma50 and price > sma50:
        bullish += 10
    elif sma50 and price < sma50:
        bearish += 10

    if rsi is not None:
        if 45 <= rsi <= 68:
            bullish += 12
        elif 32 <= rsi <= 55:
            bearish += 12
        if rsi >= 55:
            bullish += 5
        if rsi <= 45:
            bearish += 5

    if hist > 0:
        bullish += 14
    elif hist < 0:
        bearish += 14
    if hist > prev_hist:
        bullish += 6
    elif hist < prev_hist:
        bearish += 6

    if rvol >= 1.25:
        bullish += 10
        bearish += 10
    if rvol >= 1.6:
        bullish += 5
        bearish += 5

    if catalyst.get("has_catalyst"):
        impact = float(catalyst.get("catalyst_impact") or 0)
        boost = min(15, impact / 5)
        sentiment = catalyst.get("catalyst_sentiment")
        if sentiment == "bullish":
            bullish += boost
        elif sentiment == "bearish":
            bearish += boost
        else:
            bullish += boost * 0.5
            bearish += boost * 0.5

    if sma20 and _pct_diff(price, sma20) <= 2.5:
        if price >= sma20:
            bullish += 8
        else:
            bearish += 8

    direction = "bullish" if bullish >= bearish else "bearish"
    setup_strength = max(bullish, bearish)
    if setup_strength < min_setup_strength:
        return None

    weak_setup = setup_strength < 42

    entry_low, entry_high, stop, targets, hold, timeframe = _build_levels(
        direction=direction,
        price=price,
        sma20=sma20,
        sma50=sma50,
        recent_high=recent_high,
        recent_low=recent_low,
        volatility_pct=vol_pct,
    )

    stop_distance_pct = _pct_diff(price, stop)
    risk_score = round(min(90, max(18, stop_distance_pct * 12 + (100 - (rsi or 50)) * 0.15)), 1)
    confidence = round(min(92, setup_strength + (8 if catalyst.get("has_catalyst") else 0)), 1)
    opportunity = round(min(95, confidence * 0.55 + (100 - risk_score) * 0.35 + min(12, rvol * 4)), 1)
    if weak_setup:
        opportunity = round(min(38, opportunity * 0.65), 1)
        confidence = round(min(55, confidence * 0.75), 1)

    technicals = {
        "rsi": rsi,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "macd": macd.get("macd"),
        "macd_signal": macd.get("signal"),
        "macd_histogram": macd.get("histogram"),
        "relative_volume": rvol,
        "volatility_pct": vol_pct,
        "trend": direction,
        "vs_sma20_pct": round(((price / sma20) - 1) * 100, 2) if sma20 else None,
    }

    if direction == "bullish":
        if weak_setup:
            recommendation = f"Watch {symbol} — bullish lean but setup not strong enough yet"
        else:
            recommendation = f"Bullish swing on {symbol} — momentum + support alignment"
        bull_case = (
            f"Price ${price:.2f} holds above SMA20 (${sma20:.2f}). "
            f"RSI {rsi:.0f}, MACD histogram positive, volume {rvol:.1f}x average."
            if rsi and sma20
            else f"Price ${price:.2f} shows bullish swing structure with rising momentum."
        )
        bear_case = "Break below stop or fading volume would weaken the setup."
        invalidation = f"Daily close below ${stop:.2f}"
        suggested_action = f"Consider entry between ${entry_low:.2f}–${entry_high:.2f}"
    else:
        if weak_setup:
            recommendation = f"Watch {symbol} — bearish lean but setup not strong enough yet"
        else:
            recommendation = f"Bearish swing on {symbol} — weakness below key averages"
        bull_case = "Reclaim of SMA20 with volume would invalidate the short swing."
        bear_case = (
            f"Price ${price:.2f} below SMA20 (${sma20:.2f}). "
            f"RSI {rsi:.0f}, negative MACD momentum, volume {rvol:.1f}x."
            if rsi and sma20
            else f"Price ${price:.2f} shows bearish swing structure."
        )
        invalidation = f"Daily close above ${stop:.2f}"
        suggested_action = f"Consider fade/short entry between ${entry_low:.2f}–${entry_high:.2f}"

    if catalyst.get("top_headline"):
        bull_case += f" Catalyst: {catalyst['top_headline']}"

    explanation = (
        f"{direction.capitalize()} swing scored {opportunity:.0f}/100. "
        f"RSI {rsi or '—'}, RVOL {rvol:.1f}x, MACD hist {hist:+.2f}. "
        f"Hold window {hold}."
    )

    compact_chart = chart_bars[-90:] if chart_bars else []

    return StockSwingSetup(
        symbol=symbol.upper(),
        direction=direction,
        price=round(price, 2),
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop,
        profit_targets=targets,
        expected_hold_time=hold,
        timeframe=timeframe,
        technicals=technicals,
        confidence_score=confidence,
        risk_score=risk_score,
        opportunity_score=opportunity,
        recommendation=recommendation,
        explanation=explanation,
        bull_case=bull_case,
        bear_case=bear_case,
        invalidation=invalidation,
        suggested_action=suggested_action,
        scoring_snapshot={
            "direction": direction,
            "setup_strength": setup_strength,
            "weak_setup": weak_setup,
            "catalyst": catalyst,
            "chart_bars": compact_chart,
            "market_context": {
                "rsi": rsi,
                "relative_volume": rvol,
                "has_catalyst": bool(catalyst.get("has_catalyst")),
                "top_headline": catalyst.get("top_headline"),
                "trend_bullish": direction == "bullish",
            },
        },
    )


def setup_to_row(user_id: str, setup: StockSwingSetup) -> dict[str, Any]:
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    return {
        "user_id": user_id,
        "ticker": setup.symbol,
        "current_price": setup.price,
        "entry_range": {"low": setup.entry_low, "high": setup.entry_high},
        "stop_loss": setup.stop_loss,
        "profit_targets": setup.profit_targets,
        "expected_hold_time": setup.expected_hold_time,
        "timeframe": setup.timeframe,
        "technicals": setup.technicals,
        "confidence_score": setup.confidence_score,
        "risk_score": setup.risk_score,
        "opportunity_score": setup.opportunity_score,
        "recommendation": setup.recommendation,
        "explanation": setup.explanation,
        "bull_case": setup.bull_case,
        "bear_case": setup.bear_case,
        "invalidation": setup.invalidation,
        "suggested_action": setup.suggested_action,
        "risk_warning": "Stocks can gap against you. This is not financial advice.",
        "scoring_snapshot": setup.scoring_snapshot,
        "status": "active",
        "data_as_of": now,
    }
