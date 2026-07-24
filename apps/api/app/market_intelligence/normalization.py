"""Idempotent normalization for options activity events."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.market_intelligence.types import (
    DataStatus,
    NormalizedOptionsActivity,
    dec,
    money,
)


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def compute_midpoint(bid: Decimal | None, ask: Decimal | None, last: Decimal | None) -> Decimal | None:
    if bid is not None and ask is not None and ask >= bid and ask > 0:
        return money((bid + ask) / Decimal("2"))
    if last is not None and last > 0:
        return money(last)
    return None


def compute_estimated_premium(
    contracts: int | None,
    price: Decimal | None,
) -> Decimal | None:
    if contracts is None or price is None:
        return None
    # Options premium notional ≈ contracts * 100 * price
    return (Decimal(contracts) * Decimal("100") * price).quantize(Decimal("0.0001"))


def compute_volume_oi_ratio(volume: int | None, open_interest: int | None) -> Decimal | None:
    if volume is None or open_interest is None:
        return None
    if open_interest <= 0:
        return None
    return (Decimal(volume) / Decimal(open_interest)).quantize(Decimal("0.000001"))


def classify_side(bid: Decimal | None, ask: Decimal | None, price: Decimal | None) -> str:
    """Bid/ask execution classification — not directional intent."""
    if price is None or bid is None or ask is None or ask <= bid:
        return "unknown"
    mid = (bid + ask) / Decimal("2")
    spread = ask - bid
    if spread <= 0:
        return "unknown"
    # Near ask → buy aggressor; near bid → sell aggressor
    if price >= ask - (spread * Decimal("0.25")):
        return "ask"
    if price <= bid + (spread * Decimal("0.25")):
        return "bid"
    if abs(price - mid) <= spread * Decimal("0.15"):
        return "mid"
    return "unknown"


def make_idempotency_key(
    *,
    data_source: str,
    source_event_id: str | None,
    underlying: str,
    option_type: str,
    strike: Decimal,
    expiration: date,
    trade_timestamp: datetime,
    contracts: int | None,
    contract_price: Decimal | None,
) -> str:
    if source_event_id:
        raw = f"{data_source}:{source_event_id}"
    else:
        raw = "|".join(
            [
                data_source,
                underlying.upper(),
                option_type.lower(),
                str(strike),
                expiration.isoformat(),
                trade_timestamp.isoformat(),
                str(contracts or ""),
                str(contract_price or ""),
            ]
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_activity(raw: dict[str, Any], *, data_source: str, data_status: DataStatus) -> NormalizedOptionsActivity | None:
    underlying = str(raw.get("underlying") or raw.get("symbol") or "").upper().strip()
    option_type = str(raw.get("option_type") or raw.get("type") or "").lower().strip()
    if option_type not in ("call", "put") or not underlying:
        return None

    strike = money(raw.get("strike"))
    expiration = _as_date(raw.get("expiration"))
    trade_timestamp = _as_dt(raw.get("trade_timestamp") or raw.get("timestamp"))
    if expiration is None or trade_timestamp is None or strike <= 0:
        return None

    bid = money(raw["bid"]) if raw.get("bid") is not None else None
    ask = money(raw["ask"]) if raw.get("ask") is not None else None
    last = money(raw["contract_price"]) if raw.get("contract_price") is not None else (
        money(raw["last"]) if raw.get("last") is not None else None
    )
    midpoint = compute_midpoint(bid, ask, last)
    contracts = int(raw["contracts"]) if raw.get("contracts") is not None else None
    volume = int(raw["contract_volume"]) if raw.get("contract_volume") is not None else (
        int(raw["volume"]) if raw.get("volume") is not None else None
    )
    oi = int(raw["open_interest"]) if raw.get("open_interest") is not None else None
    price = last or midpoint
    premium = compute_estimated_premium(contracts, price)
    voi = compute_volume_oi_ratio(volume, oi)
    execution = raw.get("execution_class") or classify_side(bid, ask, price)

    source_event_id = str(raw["source_event_id"]) if raw.get("source_event_id") else None
    idem = raw.get("idempotency_key") or make_idempotency_key(
        data_source=data_source,
        source_event_id=source_event_id,
        underlying=underlying,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        trade_timestamp=trade_timestamp,
        contracts=contracts,
        contract_price=price,
    )

    return NormalizedOptionsActivity(
        underlying=underlying,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        trade_timestamp=trade_timestamp,
        contract_price=price,
        bid=bid,
        ask=ask,
        midpoint=midpoint,
        contracts=contracts,
        estimated_premium=premium,
        contract_volume=volume,
        open_interest=oi,
        volume_oi_ratio=voi,
        implied_volatility=dec(raw["implied_volatility"]) if raw.get("implied_volatility") is not None else None,
        delta=dec(raw["delta"]) if raw.get("delta") is not None else None,
        execution_class=str(execution) if execution else None,
        flow_class=str(raw.get("flow_class") or "unknown"),
        open_close=str(raw.get("open_close") or "unknown"),
        data_source=data_source,
        source_event_id=source_event_id,
        idempotency_key=str(idem),
        data_status=data_status,
        data_timestamp=_as_dt(raw.get("data_timestamp")) or trade_timestamp,
        raw_metadata=dict(raw.get("raw_metadata") or {}),
        underlying_price=money(raw["underlying_price"]) if raw.get("underlying_price") is not None else None,
        underlying_volume=int(raw["underlying_volume"]) if raw.get("underlying_volume") is not None else None,
        sector=str(raw["sector"]) if raw.get("sector") else None,
    )
