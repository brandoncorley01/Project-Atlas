"""FINRA ATS (dark pool) weekly transparency — official, delayed, never live."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.market_intelligence.freshness import build_freshness
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)

FINRA_WEEKLY_URL = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"


async def fetch_dark_pool_summary(*, lookback_days: int = 45, limit: int = 40) -> dict[str, Any]:
    """
    Aggregate FINRA weekly ATS share volume by symbol for the latest published week.

    This is official OTC/ATS transparency data with a regulatory lag (typically ~2 weeks
    for Tier 1). It is NOT real-time dark-pool prints and does NOT identify institutions.
    """
    end = date.today()
    start = end - timedelta(days=lookback_days)
    payload = {
        "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "summaryTypeCode", "fieldValue": "ATS_W_SMBL"},
            {"compareType": "EQUAL", "fieldName": "tierIdentifier", "fieldValue": "T1"},
        ],
        "dateRangeFilters": [
            {
                "fieldName": "weekStartDate",
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            }
        ],
        "limit": 5000,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(
                FINRA_WEEKLY_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            res.raise_for_status()
            rows = res.json()
    except Exception as exc:
        logger.warning("FINRA ATS fetch failed: %s", exc)
        return {
            "items": [],
            "count": 0,
            "week_start": None,
            "freshness": build_freshness(
                provider_name="FINRA ATS Transparency",
                data_timestamp=None,
                data_status=DataStatus.PARTIAL,
                missing_fields=["finra_ats"],
            ).to_dict(),
            "disclaimer": (
                "Could not reach FINRA ATS transparency API. Dark pool volume is omitted rather "
                "than fabricated."
            ),
            "source": "finra_ats",
            "available": False,
        }

    if not isinstance(rows, list) or not rows:
        return {
            "items": [],
            "count": 0,
            "week_start": None,
            "freshness": build_freshness(
                provider_name="FINRA ATS Transparency",
                data_timestamp=None,
                data_status=DataStatus.PARTIAL,
            ).to_dict(),
            "disclaimer": "FINRA returned no ATS rows for the requested window.",
            "source": "finra_ats",
            "available": False,
        }

    weeks = sorted(
        {str(r.get("weekStartDate")) for r in rows if r.get("weekStartDate")},
        reverse=True,
    )
    latest_week = weeks[0]
    week_rows = [r for r in rows if str(r.get("weekStartDate")) == latest_week]

    by_sym: dict[str, dict[str, float]] = defaultdict(
        lambda: {"shares": 0.0, "notional": 0.0, "trades": 0.0}
    )
    for r in week_rows:
        sym = str(r.get("issueSymbolIdentifier") or "").upper().strip()
        if not sym or len(sym) > 6:
            continue
        by_sym[sym]["shares"] += float(r.get("totalWeeklyShareQuantity") or 0)
        by_sym[sym]["notional"] += float(r.get("totalNotionalSum") or 0)
        by_sym[sym]["trades"] += float(r.get("totalWeeklyTradeCount") or 0)

    # Prior week for surge detection
    prior_week = weeks[1] if len(weeks) > 1 else None
    prior: dict[str, float] = defaultdict(float)
    if prior_week:
        for r in rows:
            if str(r.get("weekStartDate")) != prior_week:
                continue
            sym = str(r.get("issueSymbolIdentifier") or "").upper().strip()
            if sym:
                prior[sym] += float(r.get("totalWeeklyShareQuantity") or 0)

    ranked = sorted(by_sym.items(), key=lambda kv: kv[1]["shares"], reverse=True)[:limit]
    items = []
    for sym, stats in ranked:
        shares = stats["shares"]
        prev = prior.get(sym) or 0.0
        ratio = (shares / prev) if prev > 0 else None
        tag = "steady"
        if ratio is not None:
            if ratio >= 1.5:
                tag = "surge"
            elif ratio <= 0.5:
                tag = "drop"
        items.append(
            {
                "symbol": sym,
                "ats_shares": int(shares),
                "ats_notional": round(stats["notional"], 2),
                "ats_trades": int(stats["trades"]),
                "prior_week_shares": int(prev) if prev else None,
                "vs_prior_week": round(ratio, 2) if ratio is not None else None,
                "activity_tag": tag,
                "week_start": latest_week,
                "data_status": DataStatus.DELAYED.value,
                "note": "Aggregated ATS volume — not a real-time print tape; venues not named as 'smart money'.",
            }
        )

    try:
        data_ts = datetime.strptime(latest_week, "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception:
        data_ts = datetime.now(UTC) - timedelta(days=14)

    return {
        "items": items,
        "count": len(items),
        "week_start": latest_week,
        "weeks_available": weeks[:6],
        "freshness": build_freshness(
            provider_name="FINRA ATS Transparency",
            data_timestamp=data_ts,
            data_status=DataStatus.DELAYED,
        ).to_dict(),
        "disclaimer": (
            "Official FINRA ATS / OTC transparency — typically published with a multi-week "
            "regulatory delay. This is aggregated dark-pool / off-exchange volume by symbol, "
            "not live prints, and does not identify institutions or trade direction."
        ),
        "source": "finra_ats",
        "available": True,
    }
