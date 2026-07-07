"""Technical indicators computed from OHLCV bars."""

from __future__ import annotations


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def relative_volume(volumes: list[float]) -> float:
    if len(volumes) < 2:
        return 1.0
    today = volumes[-1]
    avg = sum(volumes[:-1]) / len(volumes[:-1])
    if avg <= 0:
        return 1.0
    return round(today / avg, 2)


def compute_ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)
    ema_values: list[float] = [sum(values[:period]) / period]
    for price in values[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def compute_macd(
    closes: list[float],
    *,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, float | None]:
    if len(closes) < slow + signal_period:
        return {"macd": None, "signal": None, "histogram": None}

    ema_fast = compute_ema(closes, fast)
    ema_slow = compute_ema(closes, slow)
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [f - s for f, s in zip(ema_fast[offset:], ema_slow, strict=True)]
    if len(macd_line) < signal_period:
        return {"macd": None, "signal": None, "histogram": None}

    signal_line = compute_ema(macd_line, signal_period)
    if not signal_line:
        return {"macd": None, "signal": None, "histogram": None}

    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    return {
        "macd": round(macd_val, 4),
        "signal": round(signal_val, 4),
        "histogram": round(macd_val - signal_val, 4),
    }


def recent_range_pct(closes: list[float], lookback: int = 14) -> float:
    """Average daily range as % of price — simple volatility proxy."""
    if len(closes) < lookback + 1:
        return 2.0
    ranges = [abs(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(-lookback, 0)]
    return round(sum(ranges) / len(ranges), 2)
