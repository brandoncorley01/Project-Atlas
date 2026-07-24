"""Data freshness helpers — never present simulated/delayed as live."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.market_intelligence.types import DataStatus, FreshnessMeta


def utcnow() -> datetime:
    return datetime.now(UTC)


def classify_age(age: timedelta) -> str:
    seconds = max(age.total_seconds(), 0)
    if seconds < 60:
        return "fresh"
    if seconds < 900:
        return "recent"
    if seconds < 3600:
        return "aging"
    if seconds < 86400:
        return "stale"
    return "expired"


def build_freshness(
    *,
    provider_name: str,
    data_timestamp: datetime | None,
    data_status: DataStatus,
    missing_fields: list[str] | None = None,
    now: datetime | None = None,
) -> FreshnessMeta:
    evaluation = now or utcnow()
    if data_timestamp is None:
        freshness = "unknown"
    else:
        ts = data_timestamp if data_timestamp.tzinfo else data_timestamp.replace(tzinfo=UTC)
        freshness = classify_age(evaluation - ts)
    # Hard rule: simulated/historical never claim live freshness wording alone.
    if data_status == DataStatus.SIMULATED and freshness == "fresh":
        freshness = "simulated_fresh"
    return FreshnessMeta(
        provider_name=provider_name,
        data_timestamp=data_timestamp,
        evaluation_timestamp=evaluation,
        data_status=data_status,
        data_freshness=freshness,
        missing_fields=list(missing_fields or []),
    )


def assert_not_mislabelled(status: DataStatus, claim_live: bool = False) -> None:
    if claim_live and status != DataStatus.LIVE:
        raise ValueError(f"Cannot claim live for data_status={status.value}")
