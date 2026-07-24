"""Shared types for market & options intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class DataStatus(str, Enum):
    LIVE = "live"
    DELAYED = "delayed"
    CACHED = "cached"
    HISTORICAL = "historical"
    SIMULATED = "simulated"
    PARTIAL = "partial"


class DirectionLabel(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"
    POSSIBLE_HEDGE = "possible_hedge"
    POSSIBLE_SPREAD = "possible_spread_component"


class ExitAction(str, Enum):
    ADD_REVIEW = "Add Review"
    HOLD = "Hold"
    HOLD_TRAILING = "Hold with Trailing Stop"
    TIGHTEN_STOP = "Tighten Stop"
    TAKE_PARTIAL = "Take Partial Profit"
    SCALE_OUT = "Scale Out"
    EXIT_REVIEW = "Exit Review"
    THESIS_INVALIDATED = "Thesis Invalidated"
    INSUFFICIENT_DATA = "Insufficient Data"


class SectorClass(str, Enum):
    STRENGTHENING = "Strengthening"
    LEADING = "Leading"
    WEAKENING = "Weakening"
    LAGGING = "Lagging"
    MIXED = "Mixed"
    INSUFFICIENT_DATA = "Insufficient data"


def dec(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def money(value: Any) -> Decimal:
    return dec(value).quantize(Decimal("0.000001"))


@dataclass
class FreshnessMeta:
    provider_name: str
    data_timestamp: datetime | None
    evaluation_timestamp: datetime
    data_status: DataStatus
    data_freshness: str
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "data_timestamp": self.data_timestamp.isoformat() if self.data_timestamp else None,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "data_status": self.data_status.value,
            "data_freshness": self.data_freshness,
            "missing_fields": self.missing_fields,
        }


@dataclass
class ScoreBreakdown:
    score_key: str
    score_version: str
    final_score: float
    confidence: float
    data_quality: str
    component_values: dict[str, float]
    weights: dict[str, float]
    positive_contributors: list[str]
    negative_contributors: list[str]
    missing_inputs: list[str]
    penalties: list[str]
    evaluation_timestamp: datetime
    data_timestamp: datetime | None
    data_freshness: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_key": self.score_key,
            "score_version": self.score_version,
            "final_score": round(self.final_score, 2),
            "confidence": round(self.confidence, 2),
            "data_quality": self.data_quality,
            "component_values": {k: round(v, 2) for k, v in self.component_values.items()},
            "weights": self.weights,
            "positive_contributors": self.positive_contributors,
            "negative_contributors": self.negative_contributors,
            "missing_inputs": self.missing_inputs,
            "penalties": self.penalties,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "data_timestamp": self.data_timestamp.isoformat() if self.data_timestamp else None,
            "data_freshness": self.data_freshness,
        }


@dataclass
class NormalizedOptionsActivity:
    underlying: str
    option_type: str  # call | put
    strike: Decimal
    expiration: date
    trade_timestamp: datetime
    contract_price: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    midpoint: Decimal | None
    contracts: int | None
    estimated_premium: Decimal | None
    contract_volume: int | None
    open_interest: int | None
    volume_oi_ratio: Decimal | None
    implied_volatility: Decimal | None
    delta: Decimal | None
    execution_class: str | None
    flow_class: str | None  # sweep | block | split | standard | unknown
    open_close: str | None  # opening | closing | unknown
    data_source: str
    source_event_id: str | None
    idempotency_key: str
    data_status: DataStatus
    data_timestamp: datetime | None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    underlying_price: Decimal | None = None
    underlying_volume: int | None = None
    sector: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key, val in list(d.items()):
            if isinstance(val, Decimal):
                d[key] = str(val)
            elif isinstance(val, (datetime, date)):
                d[key] = val.isoformat()
            elif isinstance(val, DataStatus):
                d[key] = val.value
        return d
