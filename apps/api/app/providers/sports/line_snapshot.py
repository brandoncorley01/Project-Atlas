"""Line snapshots for 0-credit steam detection between cache writes."""

from __future__ import annotations

from typing import Any


def line_snapshot_key(
    market_key: str,
    selection: str,
    point: float | int | None = None,
) -> str:
    if point is not None:
        return f"{market_key}|{selection}|{point}"
    return f"{market_key}|{selection}"


def build_line_snapshot(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """event_id -> snapshot_key -> FanDuel/DraftKings best american price."""
    out: dict[str, dict[str, int]] = {}
    for event in events:
        eid = str(event.get("id") or "")
        if not eid:
            continue
        bucket: dict[str, int] = {}
        for book in event.get("bookmakers") or []:
            for market in book.get("markets") or []:
                mkey = str(market.get("key") or "")
                for outcome in market.get("outcomes") or []:
                    name = str(outcome.get("name") or "")
                    price = outcome.get("price")
                    if price is None:
                        continue
                    try:
                        american = int(price)
                    except (TypeError, ValueError):
                        continue
                    point = outcome.get("point")
                    skey = line_snapshot_key(mkey, name, point)
                    prev = bucket.get(skey)
                    if prev is None or american > prev:
                        bucket[skey] = american
        if bucket:
            out[eid] = bucket
    return out


def attach_prior_lines(
    events: list[dict[str, Any]],
    prior: dict[str, dict[str, int]] | None,
) -> list[dict[str, Any]]:
    if not prior:
        return events
    for event in events:
        eid = str(event.get("id") or "")
        if eid and eid in prior:
            event["_prior_lines"] = dict(prior[eid])
    return events
