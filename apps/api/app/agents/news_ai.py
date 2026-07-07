"""News AI — classify sentiment, impact, and tickers (deterministic V1; LLM-ready later)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

BULLISH_WORDS = (
    "surge", "soar", "rally", "jump", "gain", "beat", "upgrade", "record", "high",
    "bullish", "breakout", "strong", "growth", "profit", "raises", "wins", "approval",
)
BEARISH_WORDS = (
    "fall", "drop", "sink", "plunge", "miss", "downgrade", "cut", "layoff", "lawsuit",
    "bearish", "weak", "loss", "decline", "warning", "recall", "investigation", "crash",
)
HIGH_IMPACT_WORDS = (
    "earnings", "fda", "merger", "acquisition", "guidance", "fed", "rate", "cpi", "jobs",
    "bankruptcy", "sec", "ceo", "halt", "breaking", "emergency", "tariff", "sanctions",
)
URGENT_WORDS = ("breaking", "just in", "alert", "minutes ago", "today", "now", "live")

TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")
DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")

COMMON_WORDS = {
    "A", "AI", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "ETF", "FOR", "GDP", "IPO",
    "IS", "IT", "IV", "NYSE", "CEO", "CFO", "FDA", "SEC", "FED", "US", "UK", "EU", "PM",
    "TV", "ALL", "NEW", "TOP", "BIG", "LOW", "HIGH", "BUY", "SELL", "PUT", "CALL", "ET",
    "VS", "OP", "UP", "ON", "OR", "IF", "TO", "IN", "OF", "AND", "THE", "NOW", "KEY",
    "RUN", "WAR", "OIL", "GAS", "RED", "ADD", "CAN", "MAY", "HAS", "HAD", "WAS", "ARE",
    "OUR", "OUT", "ONE", "TWO", "DAY", "WEEK", "YEAR", "SAID", "SAYS", "GET", "GOT",
    "SET", "SEE", "WAY", "WHO", "WHY", "HOW", "NOT", "BUT", "ITS", "HER", "HIS", "HIT",
    "JOB", "LOT", "OLD", "OWN", "SAY", "TOO", "USE", "VIA", "AGO", "END", "FAR", "FEW",
    "LET", "NET", "OFF", "PER", "SUN", "TAX", "TRY", "WIN", "WON", "YET", "YOU", "NYSE",
    "ETFS", "USA", "GDP", "CPI", "ATH", "EPS", "YOY", "QOQ", "MOM", "YTD", "ATH", "IPO",
}

TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("APPLE",),
    "MSFT": ("MICROSOFT",),
    "GOOGL": ("GOOGLE", "ALPHABET"),
    "GOOG": ("GOOGLE", "ALPHABET"),
    "AMZN": ("AMAZON",),
    "META": ("META", "FACEBOOK"),
    "TSLA": ("TESLA",),
    "NVDA": ("NVIDIA",),
    "AMD": ("ADVANCED MICRO",),
    "NFLX": ("NETFLIX",),
    "DIS": ("DISNEY",),
    "BA": ("BOEING",),
    "JPM": ("JPMORGAN", "JP MORGAN"),
    "GS": ("GOLDMAN",),
    "WMT": ("WALMART",),
    "COST": ("COSTCO",),
    "INTC": ("INTEL",),
    "CRM": ("SALESFORCE",),
    "UBER": ("UBER",),
    "COIN": ("COINBASE",),
}


@dataclass
class ClassifiedNews:
    sentiment: str
    impact_score: float
    time_sensitivity_score: float
    related_tickers: list[str]
    explanation: str


def classify_news(
    *,
    title: str,
    summary: str = "",
    hint_tickers: list[str] | None = None,
    known_tickers: set[str] | None = None,
    published_at: str | None = None,
) -> ClassifiedNews:
    text = f"{title} {summary}".lower()
    full_upper = f"{title} {summary}"

    bull = sum(1 for w in BULLISH_WORDS if w in text)
    bear = sum(1 for w in BEARISH_WORDS if w in text)
    if bull > bear + 1:
        sentiment = "bullish"
    elif bear > bull + 1:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    impact = 35.0
    impact += min(25, sum(6 for w in HIGH_IMPACT_WORDS if w in text))
    impact += min(15, bull + bear) * 2
    if hint_tickers:
        impact += 5

    urgency = 40.0
    urgency += min(35, sum(8 for w in URGENT_WORDS if w in text))
    if published_at:
        try:
            pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(UTC) - pub).total_seconds() / 3600
            if age_hours < 2:
                urgency += 25
            elif age_hours < 8:
                urgency += 15
            elif age_hours < 24:
                urgency += 8
        except ValueError:
            pass

    tickers = _extract_tickers(full_upper, known_tickers or set())
    tickers = filter_valid_related_tickers(
        title=title,
        summary=summary,
        tickers=tickers,
        hint_tickers=hint_tickers or [],
    )

    explanation = (
        f"{sentiment.capitalize()} tone detected ({bull} bullish / {bear} bearish signals). "
        f"Impact {min(100, impact):.0f}/100 — "
        + ("linked to " + ", ".join(tickers[:3]) if tickers else "market-wide headline")
        + "."
    )

    return ClassifiedNews(
        sentiment=sentiment,
        impact_score=round(min(100.0, impact), 2),
        time_sensitivity_score=round(min(100.0, urgency), 2),
        related_tickers=tickers[:8],
        explanation=explanation,
    )


def classify_headlines(
    headlines: list[dict[str, Any]],
    known_tickers: set[str],
    *,
    primary_symbol: str | None = None,
) -> dict[str, Any]:
    """Pick best catalyst headline for a symbol from Finnhub company news."""
    sym = (primary_symbol or "").upper().strip()
    hints = [sym] if sym else []
    best: dict[str, Any] | None = None
    best_score = 0.0

    for row in headlines:
        title = str(row.get("headline") or row.get("title") or "")
        if not title:
            continue
        classified = classify_news(
            title=title,
            summary=str(row.get("summary") or ""),
            hint_tickers=hints,
            known_tickers=known_tickers,
        )
        score = classified.impact_score + classified.time_sensitivity_score * 0.3
        if score > best_score:
            best_score = score
            best = {
                "has_catalyst": True,
                "top_headline": title,
                "catalyst_impact": classified.impact_score,
                "catalyst_sentiment": classified.sentiment,
                "news_count": len(headlines),
            }

    if best:
        return best
    return {"has_catalyst": False, "news_count": len(headlines), "catalyst_impact": 0}


def headline_mentions_symbol(title: str, summary: str = "", symbol: str = "") -> bool:
    sym = symbol.upper().strip()
    if not sym or (sym in COMMON_WORDS):
        return False
    text = f"{title} {summary}".upper()
    if f"${sym}" in text:
        return True
    if re.search(rf"\b{re.escape(sym)}\b", text):
        return True
    for alias in TICKER_ALIASES.get(sym, ()):
        if alias in text:
            return True
    return False


def filter_valid_related_tickers(
    *,
    title: str,
    summary: str,
    tickers: list[str],
    hint_tickers: list[str],
) -> list[str]:
    hints = {t.upper() for t in hint_tickers if t}
    validated: list[str] = []
    for ticker in tickers:
        sym = ticker.upper()
        if sym in COMMON_WORDS and sym not in hints:
            continue
        if sym in hints or headline_mentions_symbol(title, summary, sym):
            validated.append(sym)
    for hint in hints:
        if hint not in validated:
            validated.append(hint)
    return validated[:8]


def news_matches_symbol(
    title: str,
    summary: str,
    symbol: str,
    *,
    related_tickers: set[str] | None = None,
    company_feed: bool = False,
) -> bool:
    sym = symbol.upper().strip()
    if not sym:
        return False
    if headline_mentions_symbol(title, summary, sym):
        return True
    if company_feed and sym in (related_tickers or set()):
        return True
    return False


def sanitize_catalyst_context(context: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Drop catalyst fields when the headline does not relate to the signal symbol."""
    sym = symbol.upper().strip()
    if not sym or sym == "?":
        return context

    headline = context.get("top_headline")
    if not headline and not context.get("has_catalyst"):
        return context

    if headline and headline_mentions_symbol(str(headline), "", sym):
        return {**context, "has_catalyst": True}

    cleaned = dict(context)
    cleaned.pop("top_headline", None)
    cleaned["has_catalyst"] = False
    return cleaned


def _extract_tickers(text: str, known: set[str]) -> list[str]:
    found: list[str] = []
    for match in DOLLAR_TICKER.findall(text):
        if match not in COMMON_WORDS and (not known or match in known):
            found.append(match)
    for match in TICKER_PATTERN.findall(text):
        if match in COMMON_WORDS:
            continue
        if known and match not in known:
            continue
        if len(match) < 2:
            continue
        if match not in found:
            found.append(match)
    return found
