"""Earnings Intelligence types — real-data decision support."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class EarningsPhase(str, Enum):
    PRE_EARNINGS = "PRE_EARNINGS"
    WAITING_FOR_REPORT = "WAITING_FOR_REPORT"
    POST_RELEASE_UNCONFIRMED = "POST_RELEASE_UNCONFIRMED"
    POST_EARNINGS_CONFIRMED = "POST_EARNINGS_CONFIRMED"
    EXPIRED = "EXPIRED"


class EarningsRecType(str, Enum):
    AVOID = "AVOID"
    WATCH = "WATCH"
    MICRO_COATTAIL = "MICRO_COATTAIL"
    QUALIFIED_TRADE = "QUALIFIED_TRADE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EarningsDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    NO_EDGE = "no_directional_edge"


class EarningsStrategy(str, Enum):
    NO_TRADE = "no_trade"
    SHARES = "shares"
    ATM_OPTION = "atm_option"
    OTM_OPTION = "otm_option"
    DEBIT_SPREAD = "debit_spread"
    WAIT_POST_CONFIRM = "wait_post_earnings_confirmation"


@dataclass
class EarningsEvent:
    symbol: str
    company_name: str
    report_date: date
    release_time: str  # BMO | AMC | unknown
    phase: EarningsPhase
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    eps_actual: float | None = None
    revenue_actual: float | None = None
    guidance_note: str | None = None
    analyst_sentiment: str | None = None  # bullish | bearish | mixed | unknown
    sector: str | None = None
    sector_direction: str | None = None
    market_direction: str | None = None
    price: float | None = None
    volume: float | None = None
    support: float | None = None
    resistance: float | None = None
    historical_moves_pct: list[float] = field(default_factory=list)
    data_status: str = "simulated"
    data_source: str = "fixture"
    missing_fields: list[str] = field(default_factory=list)
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["report_date"] = self.report_date.isoformat()
        d["phase"] = self.phase.value
        return d


@dataclass
class ContractCandidate:
    option_type: str  # call | put
    strike: float
    expiration: str
    premium: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    iv: float | None
    delta: float | None
    moneyness: str  # itm | atm | otm
    spread_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyComparison:
    strategy: EarningsStrategy
    rank: int
    expected_value: float | None
    probability_of_profit: float | None
    max_loss: float | None
    breakeven_pct: float | None
    note: str
    rejected: bool = False
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        return d


@dataclass
class EarningsRecommendation:
    symbol: str
    recommendation: EarningsRecType
    direction: EarningsDirection
    phase: EarningsPhase
    strategy: EarningsStrategy
    confidence: float
    expected_move_pct: float | None
    historical_avg_move_pct: float | None
    estimated_iv_crush_pct: float | None
    breakeven_pct: float | None
    probability_of_profit: float | None
    expected_value: float | None
    max_loss: float | None
    position_size_usd: float
    entry_condition: str
    invalidation_condition: str
    profit_targets: list[str]
    expected_holding_period: str
    watching: list[str]
    why_strategy: str
    why_not_full_size: str | None
    upgrade_condition: str
    downgrade_condition: str
    cancel_condition: str
    summary: str
    alternatives: list[StrategyComparison] = field(default_factory=list)
    contract: ContractCandidate | None = None
    score: dict[str, Any] | None = None
    data_status: str = "delayed"
    evaluated_at: datetime | None = None
    watch_expires_at: str | None = None
    confirmation_condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "recommendation": self.recommendation.value,
            "direction": self.direction.value,
            "phase": self.phase.value,
            "strategy": self.strategy.value,
            "confidence": round(self.confidence, 1),
            "expected_move_pct": self.expected_move_pct,
            "historical_avg_move_pct": self.historical_avg_move_pct,
            "estimated_iv_crush_pct": self.estimated_iv_crush_pct,
            "breakeven_pct": self.breakeven_pct,
            "probability_of_profit": self.probability_of_profit,
            "expected_value": self.expected_value,
            "max_loss": self.max_loss,
            "position_size_usd": self.position_size_usd,
            "entry_condition": self.entry_condition,
            "invalidation_condition": self.invalidation_condition,
            "profit_targets": self.profit_targets,
            "expected_holding_period": self.expected_holding_period,
            "watching": self.watching,
            "why_strategy": self.why_strategy,
            "why_not_full_size": self.why_not_full_size,
            "upgrade_condition": self.upgrade_condition,
            "downgrade_condition": self.downgrade_condition,
            "cancel_condition": self.cancel_condition,
            "summary": self.summary,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "contract": self.contract.to_dict() if self.contract else None,
            "score": self.score,
            "data_status": self.data_status,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "watch_expires_at": self.watch_expires_at,
            "confirmation_condition": self.confirmation_condition,
        }
