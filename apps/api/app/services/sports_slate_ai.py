"""OpenAI ranks a sports slate from real Odds API lines — never invents prices."""

from __future__ import annotations

import logging
from typing import Any

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_SYSTEM = """You are Atlas sports desk. Rank playable FanDuel/DraftKings bets from the
candidate slate. Every candidate already has real American odds from The Odds API.
Never invent odds, lines, injuries, or scores. Balance American majors (MLB, WNBA,
NFL, NBA, NHL, MLS, MMA) with strong international edges (EPL, UCL, La Liga, etc.) —
do not collapse the board to only one geography. Return JSON only:
{
  "picks": [
    {"id": "<candidate id>", "rank": 1, "boost": 0-8, "why": "one short sentence"}
  ],
  "notes": "optional one-liner"
}
Pick at most 24 ids that already appear in the slate. Prefer positive or near-zero edge
and games starting sooner, while keeping a US + global mix."""


def _candidate_payload(row: dict[str, Any], idx: int) -> dict[str, Any]:
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    cid = str(snap.get("candidate_id") or f"c{idx}")
    return {
        "id": cid,
        "sport": row.get("sport"),
        "event": row.get("event_name"),
        "start": row.get("event_start"),
        "bet_type": row.get("bet_type"),
        "selection": row.get("selection"),
        "odds_american": row.get("odds_american"),
        "opportunity": row.get("opportunity_score"),
        "confidence": row.get("confidence_score"),
        "edge_pct": snap.get("edge_pct") or lm.get("edge_pct"),
        "preferred_book": snap.get("preferred_book") or lm.get("preferred_book"),
        "hours_to_start": snap.get("hours_to_start") or snap.get("hours_until_start"),
    }


async def rank_slate_with_openai(
    setups: list[dict[str, Any]],
    *,
    limit: int = 24,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reorder/boost setups using OpenAI; identity preserved; odds untouched."""
    if not setups or not llm_service.is_configured():
        return setups, {"openai_slate": False, "reason": "skipped"}

    for i, row in enumerate(setups):
        snap = row.setdefault("scoring_snapshot", {})
        snap.setdefault("candidate_id", f"c{i}")

    payload = [_candidate_payload(row, i) for i, row in enumerate(setups[:60])]
    try:
        result = await llm_service.complete_json(
            system=_SYSTEM,
            user=(
                "Rank the best bets for a FanDuel/DraftKings board that mixes "
                "American and international leagues. Keep both sides represented. "
                f"Candidates:\n{payload}"
            ),
            max_tokens=900,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("OpenAI slate rank failed: %s", exc)
        return setups, {"openai_slate": False, "reason": str(exc)[:120]}

    if not result or not isinstance(result.get("picks"), list):
        return setups, {"openai_slate": False, "reason": "empty_response"}

    by_id = {
        str((r.get("scoring_snapshot") or {}).get("candidate_id")): r for r in setups
    }
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pick in result["picks"][:limit]:
        if not isinstance(pick, dict):
            continue
        cid = str(pick.get("id") or "")
        row = by_id.get(cid)
        if not row or cid in seen:
            continue
        seen.add(cid)
        boost = max(0.0, min(8.0, float(pick.get("boost") or 0)))
        if boost:
            row["opportunity_score"] = round(float(row.get("opportunity_score") or 0) + boost, 1)
        snap = row.setdefault("scoring_snapshot", {})
        snap["openai_rank"] = int(pick.get("rank") or len(ranked) + 1)
        snap["openai_boost"] = boost
        why = str(pick.get("why") or "").strip()
        if why and not snap.get("openai_why"):
            snap["openai_why"] = why[:220]
            existing = str(row.get("explanation") or "")
            row["explanation"] = f"{existing} Atlas AI: {why}".strip() if existing else f"Atlas AI: {why}"
        ranked.append(row)

    # Keep remaining deterministic picks after AI-ranked ones.
    for row in setups:
        cid = str((row.get("scoring_snapshot") or {}).get("candidate_id") or "")
        if cid not in seen:
            ranked.append(row)

    meta = {
        "openai_slate": True,
        "openai_ranked": len(seen),
        "notes": str(result.get("notes") or "")[:200] or None,
    }
    return ranked, meta
