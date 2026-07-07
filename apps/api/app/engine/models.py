from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class SignalModule(str, Enum):
    OPTIONS = "options"
    STOCK = "stock"
    SPORTS = "sports"
    PARLAY = "parlay"


@dataclass
class CandidateOpportunity:
    module: SignalModule
    symbol: str
    option_type: str | None = None
    strike: float | None = None
    expiration: date | None = None
    premium: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int = 0
    open_interest: int = 0
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    implied_volatility: float | None = None
    relative_volume: float = 1.0
    has_catalyst: bool = False
    trend_bullish: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def days_to_expiration(self) -> int:
        if not self.expiration:
            return 0
        return max((self.expiration - date.today()).days, 0)

    @property
    def bid_ask_spread_pct(self) -> float:
        if self.bid is None or self.ask is None or self.ask <= 0:
            return 100.0
        return ((self.ask - self.bid) / self.ask) * 100


@dataclass
class ScoredOpportunity:
    candidate: CandidateOpportunity
    confidence_score: float
    risk_score: float
    opportunity_score: float
    scoring_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedOpportunity:
    scored: ScoredOpportunity
    entry_zone: dict[str, float]
    profit_targets: list[float]
    max_loss: float
    expected_hold_time: str
    stop_loss: float | None = None


@dataclass
class ExplainedSignal:
    planned: PlannedOpportunity
    recommendation: str
    explanation: str
    bull_case: str
    bear_case: str
    invalidation: str
    suggested_action: str
    risk_warning: str = (
        "Options can expire worthless. This is decision support only — not financial advice."
    )
